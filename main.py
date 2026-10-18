import os
import sqlite3
import uuid
import webbrowser
import pytesseract
from expiry_ocr import detect_expiry_date
from recipe_recommender import recommend_recipes
from datetime import datetime, date
from threading import Timer

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash
)
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from food_model import recognize_food
from freshness_model import predict_freshness


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

app.secret_key = "freshguard_secret_key_2026"

DATABASE = "freshguard.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():

    connection = sqlite3.connect(DATABASE)

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_database():

    connection = get_db_connection()

    cursor = connection.cursor()

    # --------------------------------------------------------
    # USERS TABLE
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT NOT NULL UNIQUE,

            email TEXT NOT NULL UNIQUE,

            password TEXT NOT NULL,

            created_at TEXT NOT NULL
        )
        """
    )

    # --------------------------------------------------------
    # FOOD ITEMS TABLE
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS food_items (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            food_name TEXT NOT NULL,

            category TEXT,

            quantity TEXT,

            purchase_date TEXT,

            expiry_date TEXT NOT NULL,

            storage TEXT,

            status TEXT,
            image_path TEXT,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
        )
        """
    )
    
    connection.execute("""
            CREATE TABLE IF NOT EXISTS shopping_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                quantity TEXT,
                is_purchased INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
            )
        """)
    
    # --------------------------------------------------------
    # MONTHLY BUDGET TABLE
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS monthly_budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            budget REAL NOT NULL DEFAULT 0,
            UNIQUE(user_id, month),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )


        # --------------------------------------------------------
    # DATABASE MIGRATION
    # Add image_path to existing food_items table
    # --------------------------------------------------------

    try:

        cursor.execute(
            "ALTER TABLE food_items ADD COLUMN image_path TEXT"
        )

    except sqlite3.OperationalError:

        # Column already exists
        pass
        # --------------------------------------------------------
    # DATABASE MIGRATION
    # Add cost column to existing food_items table
    # --------------------------------------------------------

    try:
        cursor.execute(
            "ALTER TABLE food_items ADD COLUMN cost REAL DEFAULT 0"
        )
    except sqlite3.OperationalError:
        # Column already exists
        pass
    # Add category to food history for spending analysis
    try:
        cursor.execute(
        "ALTER TABLE food_history ADD COLUMN category TEXT"
        )
    except sqlite3.OperationalError:
        pass

    # --------------------------------------------------------
    # FOOD HISTORY TABLE
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS food_history (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            food_id INTEGER,

            food_name TEXT,

            action TEXT,

            action_date TEXT,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
        )
        """
    )
        # --------------------------------------------------------
    # DATABASE MIGRATION
    # Add cost to existing food_history table
    # --------------------------------------------------------

    try:
        cursor.execute(
            "ALTER TABLE food_history ADD COLUMN cost REAL DEFAULT 0"
        )
    except sqlite3.OperationalError:
        # Column already exists
        pass

    connection.commit()

    connection.close()


init_database()


# ============================================================
# LOGIN MANAGER
# ============================================================

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "login"


class User(UserMixin):

    def __init__(
        self,
        user_id,
        username,
        email
    ):

        self.id = user_id
        self.username = username
        self.email = email


@login_manager.user_loader
def load_user(user_id):

    connection = get_db_connection()

    user = connection.execute(
        """
        SELECT
            id,
            username,
            email
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    connection.close()

    if user:

        return User(
            user["id"],
            user["username"],
            user["email"]
        )

    return None


# ============================================================
# EXPIRY STATUS
# ============================================================

def calculate_status(expiry_date):

    try:

        expiry = datetime.strptime(
            expiry_date,
            "%Y-%m-%d"
        ).date()

        today = date.today()

        days_left = (
            expiry - today
        ).days

        if days_left < 0:

            return "EXPIRED"

        elif days_left == 0:

            return "EXPIRES TODAY"

        elif days_left <= 2:

            return "EXPIRING SOON"

        elif days_left <= 7:

            return "USE SOON"

        else:

            return "FRESH"

    except Exception:

        return "UNKNOWN"


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    if current_user.is_authenticated:

        return redirect(
            url_for("dashboard")
        )

    return redirect(
        url_for("login")
    )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if current_user.is_authenticated:

        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not username:

            return render_template(
                "register.html",
                error="Please enter a username."
            )

        if not email:

            return render_template(
                "register.html",
                error="Please enter an email."
            )

        if not password:

            return render_template(
                "register.html",
                error="Please enter a password."
            )

        if len(password) < 6:

            return render_template(
                "register.html",
                error="Password must contain at least 6 characters."
            )

        # ----------------------------------------------------
        # DATABASE CONNECTION
        # ----------------------------------------------------

        connection = get_db_connection()

        # ----------------------------------------------------
        # CHECK USERNAME
        # ----------------------------------------------------

        existing_username = connection.execute(
            """
            SELECT id
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

        if existing_username:

            connection.close()

            return render_template(
                "register.html",
                error="Username already exists."
            )

        # ----------------------------------------------------
        # CHECK EMAIL
        # ----------------------------------------------------

        existing_email = connection.execute(
            """
            SELECT id
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        if existing_email:

            connection.close()

            return render_template(
                "register.html",
                error="Email already registered."
            )

        # ----------------------------------------------------
        # HASH PASSWORD
        # ----------------------------------------------------

        hashed_password = generate_password_hash(
            password
        )

        created_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # ----------------------------------------------------
        # CREATE USER
        # ----------------------------------------------------

        try:

            connection.execute(
                """
                INSERT INTO users
                (
                    username,
                    email,
                    password,
                    created_at
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    username,
                    email,
                    hashed_password,
                    created_at
                )
            )

            connection.commit()

        except sqlite3.IntegrityError as error:

            connection.rollback()

            connection.close()

            return render_template(
                "register.html",
                error=f"Registration failed: {error}"
            )

        except Exception as error:

            connection.rollback()

            connection.close()

            return render_template(
                "register.html",
                error=f"Registration failed: {error}"
            )

        connection.close()

        flash(
            "Registration successful! Please login.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )


# ============================================================
# LOGIN - EMAIL + PASSWORD
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if current_user.is_authenticated:

        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        # IMPORTANT:
        # Login now uses EMAIL, not username.

        email = request.form.get(
            "email",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not email:

            return render_template(
                "login.html",
                error="Please enter your email."
            )

        if not password:

            return render_template(
                "login.html",
                error="Please enter your password."
            )

        # ----------------------------------------------------
        # FIND USER BY EMAIL
        # ----------------------------------------------------

        connection = get_db_connection()

        user = connection.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        connection.close()

        # ----------------------------------------------------
        # CHECK USER
        # ----------------------------------------------------

        if user:

            password_correct = check_password_hash(
                user["password"],
                password
            )

            if password_correct:

                user_object = User(
                    user["id"],
                    user["username"],
                    user["email"]
                )

                login_user(
                    user_object
                )

                return redirect(
                    url_for("dashboard")
                )

        return render_template(
            "login.html",
            error="Invalid email or password."
        )

    return render_template(
        "login.html"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect(
        url_for("login")
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    search = request.args.get(
        "search",
        ""
    ).strip()

    selected_category = request.args.get(
        "category",
        ""
    ).strip()

    selected_status = request.args.get(
        "status",
        ""
    ).strip()


    connection = get_db_connection()


    # ========================================================
    # GET USER FOOD ITEMS
    # ========================================================

    query = """
        SELECT *
        FROM food_items
        WHERE user_id = ?
    """

    parameters = [
        current_user.id
    ]


    # ========================================================
    # SEARCH
    # ========================================================

    if search:

        query += """
            AND food_name LIKE ?
        """

        parameters.append(
            "%" + search + "%"
        )


    # ========================================================
    # CATEGORY FILTER
    # ========================================================

    if selected_category:

        query += """
            AND category = ?
        """

        parameters.append(
            selected_category
        )


    # ========================================================
    # SORT BY EXPIRY DATE
    # ========================================================

    query += """
        ORDER BY expiry_date ASC
    """


    food_items = connection.execute(
        query,
        parameters
    ).fetchall()


    # ========================================================
    # CALCULATE CURRENT STATUS
    # ========================================================

    
        # ========================================================
    # CALCULATE STATUS AND EXPIRY COUNTDOWN
    # ========================================================

    updated_items = []
    today = date.today()

    for item in food_items:
        item_dict = dict(item)

        try:
            expiry = datetime.strptime(
                item["expiry_date"], "%Y-%m-%d"
            ).date()

            days_left = (expiry - today).days

            item_dict["days_left"] = days_left
            item_dict["status"] = calculate_status(
                item["expiry_date"]
            )

            if days_left < 0:
                item_dict["expiry_label"] = (
                    f"Expired {abs(days_left)} day(s) ago"
                )
            elif days_left == 0:
                item_dict["expiry_label"] = "Expires today"
            elif days_left == 1:
                item_dict["expiry_label"] = "Expires tomorrow"
            elif days_left <= 3:
                item_dict["expiry_label"] = (
                    f"Expires in {days_left} days"
                )
            else:
                item_dict["expiry_label"] = (
                    f"{days_left} days left"
                )

        except (ValueError, TypeError):
            item_dict["days_left"] = None
            item_dict["expiry_label"] = "Expiry date unavailable"
            item_dict["status"] = "UNKNOWN"

        updated_items.append(item_dict)

    # ========================================================
    # EXPIRY ALERTS
    # ========================================================

    expiry_alerts = [
        item
        for item in updated_items
        if item["days_left"] is not None
        and item["days_left"] <= 3
    ]
    # ========================================================
    # DASHBOARD SUMMARY COUNTS
    # ========================================================

    total_items = len(updated_items)

    fresh_items = sum(
        1 for item in updated_items
        if item["status"] == "FRESH"
    )

    expiring_soon = sum(
        1 for item in updated_items
        if item["days_left"] is not None
        and 0 <= item["days_left"] <= 3
    )

    expired_items = sum(
        1 for item in updated_items
        if item["days_left"] is not None
        and item["days_left"] < 0
    )



    # ========================================================
    # STATUS FILTER
    # ========================================================

    if selected_status:

        updated_items = [

            item

            for item in updated_items

            if item["status"] == selected_status

        ]


    # ========================================================
    # CATEGORIES
    # ========================================================

    categories = connection.execute(
        """
        SELECT DISTINCT category
        FROM food_items
        WHERE user_id = ?
        AND category IS NOT NULL
        AND category != ''
        ORDER BY category
        """,
        (current_user.id,)
    ).fetchall()


    connection.close()


    # ========================================================
    # RENDER DASHBOARD
    # ========================================================

    return render_template(

        "dashboard.html",

        food_items=updated_items,

        expiry_alerts=expiry_alerts,

        categories=categories,

        search=search,

        selected_category=selected_category,

        selected_status=selected_status,
        total_items=total_items,

    fresh_items=fresh_items,

    expiring_soon=expiring_soon,

    expired_items=expired_items

    )

@app.route("/food-list/<category>")
@login_required
def food_list(category):

    allowed_categories = [
        "all",
        "fresh",
        "expiring",
        "expired"
    ]

    if category not in allowed_categories:
        return "Invalid food list category", 404

    connection = get_db_connection()

    rows = connection.execute(
        """
        SELECT *
        FROM food_items
        WHERE user_id = ?
        ORDER BY expiry_date ASC
        """,
        (current_user.id,)
    ).fetchall()

    connection.close()

    food_items = []
    today = date.today()

    for item in rows:
        item_dict = dict(item)

        try:
            expiry = datetime.strptime(
                item["expiry_date"], "%Y-%m-%d"
            ).date()

            days_left = (expiry - today).days

            item_dict["days_left"] = days_left
            item_dict["status"] = calculate_status(
                item["expiry_date"]
            )

            if days_left < 0:
                item_dict["expiry_label"] = (
                    f"Expired {abs(days_left)} day(s) ago"
                )
            elif days_left == 0:
                item_dict["expiry_label"] = "Expires today"
            elif days_left == 1:
                item_dict["expiry_label"] = "Expires tomorrow"
            else:
                item_dict["expiry_label"] = (
                    f"{days_left} days left"
                )

        except (ValueError, TypeError):
            item_dict["days_left"] = None
            item_dict["status"] = "UNKNOWN"
            item_dict["expiry_label"] = "Expiry date unavailable"

        food_items.append(item_dict)

    if category == "fresh":
        food_items = [
            item for item in food_items
            if item["status"] == "FRESH"
        ]

    elif category == "expiring":
        food_items = [
            item for item in food_items
            if item["days_left"] is not None
            and 0 <= item["days_left"] <= 3
        ]

    elif category == "expired":
        food_items = [
            item for item in food_items
            if item["days_left"] is not None
            and item["days_left"] < 0
        ]

    titles = {
        "all": "All Food Items",
        "fresh": "Fresh Items",
        "expiring": "Expiring Soon",
        "expired": "Expired Items"
    }

    return render_template(
        "food_list.html",
        food_items=food_items,
        page_title=titles[category]
    )


@app.route("/recipes")
@login_required
def recipes():
    connection = get_db_connection()

    rows = connection.execute(
        """
        SELECT food_name
        FROM food_items
        WHERE user_id = ?
        AND status != 'CONSUMED'
        """,
        (current_user.id,)
    ).fetchall()

    connection.close()

    food_names = [row["food_name"] for row in rows]

    recommendations = recommend_recipes(food_names)

    return render_template(
        "recipes.html",
        recommendations=recommendations
    )


# ============================================================
# ADD FOOD
# ============================================================


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_food():

    shopping_item_id = request.args.get(
        "shopping_item_id", type=int
    )

    connection = get_db_connection()

    # Get the shopping item when arriving from the shopping list
    shopping_item = None

    if shopping_item_id:
        shopping_item = connection.execute(
            """
            SELECT *
            FROM shopping_list
            WHERE id = ? AND user_id = ?
            """,
            (shopping_item_id, current_user.id)
        ).fetchone()

        if shopping_item is None:
            connection.close()
            return redirect(url_for("shopping_list"))

    if request.method == "POST":

        food_name = request.form.get(
            "food_name", ""
        ).strip()

        category = request.form.get(
            "category", ""
        ).strip()

        quantity = request.form.get(
            "quantity", ""
        ).strip()
        cost_input = request.form.get(
            "cost", "0"
        ).strip()

        try:
            cost = float(cost_input or 0)

            if cost < 0:
                raise ValueError("Cost cannot be negative.")

        except ValueError:
            connection.close()
            return render_template(
        "add_food.html",
        error="Please enter a valid non-negative cost.",
        food_name=food_name,
        category=category,
        quantity=quantity,
        purchase_date=request.form.get("purchase_date", ""),
        expiry_date=request.form.get("expiry_date", ""),
        storage_location=request.form.get("storage_location", ""),
        image_path=request.form.get("image_path", ""),
        shopping_item_id=shopping_item_id
    )

        purchase_date = request.form.get(
            "purchase_date", ""
        ).strip()

        expiry_date = request.form.get(
            "expiry_date", ""
        ).strip()

        storage = request.form.get(
            "storage_location", ""
        ).strip()

        image_path = request.form.get(
            "image_path", ""
        ).strip()

        # Keep the shopping-list link through form submission
        shopping_item_id = request.form.get(
            "shopping_item_id", type=int
        )

        if not food_name:
            connection.close()
            return render_template(
                "add_food.html",
                error="Please enter food name.",
                food_name=food_name,
                category=category,
                quantity=quantity,
                purchase_date=purchase_date,
                expiry_date=expiry_date,
                storage_location=storage,
                image_path=image_path,
                shopping_item_id=shopping_item_id
            )

        if not expiry_date:
            connection.close()
            return render_template(
                "add_food.html",
                error="Please enter expiry date.",
                food_name=food_name,
                category=category,
                quantity=quantity,
                purchase_date=purchase_date,
                expiry_date=expiry_date,
                storage_location=storage,
                image_path=image_path,
                shopping_item_id=shopping_item_id
            )

        # If linked to a shopping item, verify ownership again
        if shopping_item_id:
            linked_item = connection.execute(
                """
                SELECT id
                FROM shopping_list
                WHERE id = ? AND user_id = ?
                """,
                (shopping_item_id, current_user.id)
            ).fetchone()

            if linked_item is None:
                connection.close()
                return redirect(url_for("shopping_list"))

        status = calculate_status(expiry_date)

        cursor = connection.execute(
            """
            INSERT INTO food_items
            (
                user_id,
                food_name,
                category,
                quantity,
                purchase_date,
                expiry_date,
                storage,
                status,
                image_path,
                cost
            )
            VALUES (?, ?, ?, ?,?, ?, ?, ?, ?, ?)
            """,
            (
                current_user.id,
                food_name,
                category,
                quantity,
                purchase_date,
                expiry_date,
                storage,
                status,
                image_path,
                cost
            )
        )

        food_id = cursor.lastrowid

        # Record the food addition in history
        connection.execute(
            """
            INSERT INTO food_history
            (
                user_id,
                food_id,
                food_name,
                action,
                action_date,
                cost,
                category
            )
            VALUES (?, ?, ?, ?, ?,?,?)
            """,
            (
                current_user.id,
                food_id,
                food_name,
                "Added",
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                cost,
                category
            )
        )

        # Mark the shopping item as purchased after saving the food
        if shopping_item_id:
            connection.execute(
                """
                UPDATE shopping_list
                SET is_purchased = 1
                WHERE id = ? AND user_id = ?
                """,
                (shopping_item_id, current_user.id)
            )

        connection.commit()
        connection.close()

        # Return to the shopping list if this came from Bought
        if shopping_item_id:
            return redirect(url_for("shopping_list"))

        return redirect(url_for("dashboard"))

    # Prepare initial form values
    if shopping_item:
        food_name = shopping_item["item_name"]
        quantity = shopping_item["quantity"] or ""
    else:
        food_name = request.args.get("food_name", "")
        quantity = request.args.get("quantity", "")

    category = request.args.get("category", "")
    purchase_date = request.args.get("purchase_date", "")
    expiry_date = request.args.get("expiry_date", "")
    image_path = request.args.get("image_path", "")
    storage_location = request.args.get("storage_location", "")

    connection.close()

    return render_template(
        "add_food.html",
        food_name=food_name,
        category=category,
        quantity=quantity,
        purchase_date=purchase_date,
        expiry_date=expiry_date,
        storage_location=storage_location,
        image_path=image_path,
        shopping_item_id=shopping_item_id,
        error=None
    )

# ============================================================
# CONSUME FOOD
# ============================================================

@app.route(
    "/consume/<int:food_id>"
)
@login_required
def consume_food(food_id):

    connection = get_db_connection()

    food = connection.execute(
        """
        SELECT *
        FROM food_items
        WHERE id = ?
        AND user_id = ?
        """,
        (
            food_id,
            current_user.id
        )
    ).fetchone()

    if food:

        connection.execute(
            """
            INSERT INTO food_history
            (
                user_id,
                food_id,
                food_name,
                action,
                action_date
            )
            VALUES
            (?, ?, ?, ?, ?)
            """,
            (
                current_user.id,
                food_id,
                food["food_name"],
                "Consumed",
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )

        connection.execute(
            """
            DELETE FROM food_items
            WHERE id = ?
            AND user_id = ?
            """,
            (
                food_id,
                current_user.id
            )
        )

        connection.commit()

    connection.close()

    return redirect(
        url_for("dashboard")
    )

@app.route("/waste/<int:food_id>")
@login_required
def waste_food(food_id):
    connection = get_db_connection()

    food = connection.execute(
        """
        SELECT *
        FROM food_items
        WHERE id = ?
          AND user_id = ?
        """,
        (food_id, current_user.id)
    ).fetchone()

    if food:
        connection.execute(
            """
            INSERT INTO food_history
            (
                user_id,
                food_id,
                food_name,
                action,
                action_date,
                cost
            )
            VALUES (?, ?, ?,?, ?, ?)
            """,
            (
                current_user.id,
                food_id,
                food["food_name"],
                "Wasted",
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ), food["cost"] or 0
            )
        )

        connection.execute(
            """
            DELETE FROM food_items
            WHERE id = ?
              AND user_id = ?
            """,
            (food_id, current_user.id)
        )

        connection.commit()

    connection.close()

    return redirect(url_for("dashboard"))



# ============================================================
# DELETE FOOD
# ============================================================

@app.route(
    "/delete/<int:food_id>"
)
@login_required
def delete_food(food_id):

    connection = get_db_connection()

    food = connection.execute(
        """
        SELECT *
        FROM food_items
        WHERE id = ?
        AND user_id = ?
        """,
        (
            food_id,
            current_user.id
        )
    ).fetchone()

    if food:

        connection.execute(
            """
            INSERT INTO food_history
            (
                user_id,
                food_id,
                food_name,
                action,
                action_date
            )
            VALUES
            (?, ?, ?, ?, ?)
            """,
            (
                current_user.id,
                food_id,
                food["food_name"],
                "Deleted",
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )

        connection.execute(
            """
            DELETE FROM food_items
            WHERE id = ?
            AND user_id = ?
            """,
            (
                food_id,
                current_user.id
            )
        )

        connection.commit()

    connection.close()

    return redirect(
        url_for("dashboard")
    )


# ============================================================
# HISTORY
# ============================================================

@app.route("/history")
@login_required
def history():
    connection = get_db_connection()

    # ---------------------------------------------------------
    # 1. ADDED FOOD
    # ---------------------------------------------------------
    added_foods = connection.execute(
        """
        SELECT *
        FROM food_history
        WHERE user_id = ?
          AND action = 'Added'
        ORDER BY action_date DESC
        """,
        (current_user.id,)
    ).fetchall()

    # ---------------------------------------------------------
    # 2. CONSUMED FOOD
    # ---------------------------------------------------------
    consumed_foods = connection.execute(
        """
        SELECT *
        FROM food_history
        WHERE user_id = ?
          AND action = 'Consumed'
        ORDER BY action_date DESC
        """,
        (current_user.id,)
    ).fetchall()

    # ---------------------------------------------------------
    # 3. CURRENT FOOD INVENTORY
    # ---------------------------------------------------------
    current_foods = connection.execute(
        """
        SELECT *
        FROM food_items
        WHERE user_id = ?
        ORDER BY expiry_date ASC
        """,
        (current_user.id,)
    ).fetchall()

    connection.close()

    # ---------------------------------------------------------
    # 4. SEPARATE EXPIRING AND EXPIRED FOOD
    # ---------------------------------------------------------
    expiring_foods = []
    expired_foods = []

    for food in current_foods:
        food_data = dict(food)

        status = calculate_status(food["expiry_date"])

        food_data["status"] = status

        if status == "EXPIRED":
            expired_foods.append(food_data)

        elif status in [
            "EXPIRES TODAY",
            "EXPIRING SOON",
            "USE SOON"
        ]:
            expiring_foods.append(food_data)

    # ---------------------------------------------------------
    # 5. RENDER HISTORY DASHBOARD
    # ---------------------------------------------------------
    return render_template(
        "history.html",
        added_foods=added_foods,
        consumed_foods=consumed_foods,
        expiring_foods=expiring_foods,
        expired_foods=expired_foods
    )

@app.route("/analytics")
@login_required
def analytics():
    connection = get_db_connection()

    # Count food items currently in inventory
    total_inventory = connection.execute(
        """
        SELECT COUNT(*) AS total
        FROM food_items
        WHERE user_id = ?
        """,
        (current_user.id,)
    ).fetchone()["total"]

    # Count food items added
    total_added = connection.execute(
        """
        SELECT COUNT(*) AS total
        FROM food_history
        WHERE user_id = ?
          AND action = 'Added'
        """,
        (current_user.id,)
    ).fetchone()["total"]

    # Count food items consumed
    total_consumed = connection.execute(
        """
        SELECT COUNT(*) AS total
        FROM food_history
        WHERE user_id = ?
          AND action = 'Consumed'
        """,
        (current_user.id,)
    ).fetchone()["total"]

    # Count food items currently expired
    expired_rows = connection.execute(
        """
        SELECT expiry_date
        FROM food_items
        WHERE user_id = ?
        """,
        (current_user.id,)
    ).fetchall()
    
    # Count food items recorded as wasted
    total_wasted = connection.execute(
        """
        SELECT COUNT(*) AS total
        FROM food_history
        WHERE user_id = ?
          AND action = 'Wasted'
        """,
        (current_user.id,)
    ).fetchone()["total"]
    
    # Find foods most frequently recorded as wasted
    waste_insights = connection.execute(
        """
        SELECT
            food_name,
            COUNT(*) AS waste_count
        FROM food_history
        WHERE user_id = ?
          AND action = 'Wasted'
        GROUP BY food_name
        ORDER BY waste_count DESC, food_name ASC
        """,
        (current_user.id,)
    ).fetchall()
        # Total grocery spending recorded in food history
    total_grocery_spending = connection.execute(
        """
        SELECT COALESCE(SUM(cost), 0) AS total
        FROM food_history
        WHERE user_id = ?
          AND action = 'Added'
        """,
        (current_user.id,)
    ).fetchone()["total"]

    # Total cost of food recorded as wasted
    total_waste_cost = connection.execute(
        """
        SELECT COALESCE(SUM(cost), 0) AS total
        FROM food_history
        WHERE user_id = ?
          AND action = 'Wasted'
        """,
        (current_user.id,)
    ).fetchone()["total"]

    # Estimated value of food currently in inventory
    current_inventory_value = connection.execute(
        """
        SELECT COALESCE(SUM(cost), 0) AS total
        FROM food_items
        WHERE user_id = ?
        """,
        (current_user.id,)
    ).fetchone()["total"]
        # Monthly grocery spending
    monthly_spending = connection.execute(
        """
        SELECT
            strftime('%Y-%m', action_date) AS month,
            COALESCE(SUM(cost), 0) AS total
        FROM food_history
        WHERE user_id = ?
          AND action = 'Added'
        GROUP BY strftime('%Y-%m', action_date)
        ORDER BY month DESC
        """,
        (current_user.id,)
    ).fetchall()
        


    connection.close()

    total_expired = sum(
        1
        for item in expired_rows
        if calculate_status(item["expiry_date"]) == "EXPIRED"
    )

    return render_template(
        "analytics.html",
        total_inventory=total_inventory,
        total_added=total_added,
        total_consumed=total_consumed,
        total_expired=total_expired,
        total_wasted=total_wasted,
        waste_insights=waste_insights,
                total_grocery_spending=total_grocery_spending,
        total_waste_cost=total_waste_cost,
        current_inventory_value=current_inventory_value,
                monthly_spending=monthly_spending,
    )
# ============================================================
# SPENDING ANALYSIS
# ============================================================

@app.route("/spending-analysis")
@login_required
def spending_analysis():

    connection = get_db_connection()

    # Selected month; default to the current month
    selected_month = request.args.get(
        "month",
        date.today().strftime("%Y-%m")
    )

    # Validate the month format
    try:
        datetime.strptime(selected_month, "%Y-%m")
    except ValueError:
        selected_month = date.today().strftime("%Y-%m")

    # Spending grouped by food category for the selected month
    category_spending = connection.execute(
        """
        SELECT
            COALESCE(NULLIF(category, ''), 'Uncategorized')
                AS category,
            COALESCE(SUM(cost), 0) AS total
        FROM food_history
        WHERE user_id = ?
          AND action = 'Added'
          AND strftime('%Y-%m', action_date) = ?
        GROUP BY COALESCE(NULLIF(category, ''), 'Uncategorized')
        ORDER BY total DESC
        """,
        (current_user.id, selected_month)
    ).fetchall()

    # Total spending for the selected month
    monthly_total = sum(
        row["total"] or 0
        for row in category_spending
    )

    # Available months with recorded purchases
    available_months = connection.execute(
        """
        SELECT DISTINCT strftime('%Y-%m', action_date) AS month
        FROM food_history
        WHERE user_id = ?
          AND action = 'Added'
          AND action_date IS NOT NULL
          AND strftime('%Y-%m', action_date) IS NOT NULL
        ORDER BY month DESC
        """,
        (current_user.id,)
    ).fetchall()

    connection.close()

    # Include the current month even if no purchases exist yet
    months = [
        row["month"]
        for row in available_months
        if row["month"]
    ]

    if selected_month not in months:
        months.append(selected_month)

    months.sort(reverse=True)

    return render_template(
        "spending_analysis.html",
        category_spending=category_spending,
        monthly_total=monthly_total,
        selected_month=selected_month,
        months=months
    )

# ============================================================
# MONTHLY BUDGET
# ============================================================

@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget_tracker():

    connection = get_db_connection()

    selected_month = request.args.get(
        "month",
        date.today().strftime("%Y-%m")
    )

    # Validate the selected month
    try:
        datetime.strptime(selected_month, "%Y-%m")
    except ValueError:
        selected_month = date.today().strftime("%Y-%m")

    if request.method == "POST":

        selected_month = request.form.get(
            "month",
            date.today().strftime("%Y-%m")
        )

        try:
            datetime.strptime(selected_month, "%Y-%m")
        except ValueError:
            selected_month = date.today().strftime("%Y-%m")

        try:
            budget_amount = float(
                request.form.get("budget", "0")
            )

            if budget_amount < 0:
                raise ValueError

        except ValueError:
            connection.close()
            flash("Please enter a valid non-negative budget.", "error")
            return redirect(
                url_for("budget_tracker", month=selected_month)
            )

        connection.execute(
            """
            INSERT INTO monthly_budgets (user_id, month, budget)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, month)
            DO UPDATE SET budget = excluded.budget
            """,
            (current_user.id, selected_month, budget_amount)
        )

        connection.commit()

        flash("Monthly budget saved successfully!", "success")

        connection.close()

        return redirect(
            url_for("budget_tracker", month=selected_month)
        )

    # Get the budget for the selected month
    budget_row = connection.execute(
        """
        SELECT budget
        FROM monthly_budgets
        WHERE user_id = ? AND month = ?
        """,
        (current_user.id, selected_month)
    ).fetchone()

    monthly_budget = (
        budget_row["budget"] if budget_row else 0
    )

    # Calculate purchases for the selected month
    spent_row = connection.execute(
        """
        SELECT COALESCE(SUM(cost), 0) AS total
        FROM food_history
        WHERE user_id = ?
          AND action = 'Added'
          AND strftime('%Y-%m', action_date) = ?
        """,
        (current_user.id, selected_month)
    ).fetchone()

    total_spent = spent_row["total"] or 0
    remaining = monthly_budget - total_spent

    # Budget status
    if monthly_budget <= 0:
        budget_status = "Set a budget to start tracking."
    elif remaining < 0:
        budget_status = "Budget exceeded!"
    elif total_spent >= monthly_budget * 0.8:
        budget_status = "Warning: You have used at least 80% of your budget."
    else:
        budget_status = "You are within your budget."

    connection.close()

    return render_template(
        "budget.html",
        selected_month=selected_month,
        monthly_budget=monthly_budget,
        total_spent=total_spent,
        remaining=remaining,
        budget_status=budget_status
    )


@app.route("/shopping-list", methods=["GET", "POST"])
@login_required
def shopping_list():
    connection = get_db_connection()

    if request.method == "POST":
        item_name = request.form.get(
            "item_name", ""
        ).strip()

        quantity = request.form.get(
            "quantity", ""
        ).strip()

        if item_name:
            connection.execute(
                """
                INSERT INTO shopping_list
                (user_id, item_name, quantity, is_purchased, created_at)
                VALUES (?, ?, ?, 0, ?)
                """,
                (
                    current_user.id,
                    item_name,
                    quantity,
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )
            )
            connection.commit()

    items = connection.execute(
        """
        SELECT *
        FROM shopping_list
        WHERE user_id = ?
        ORDER BY is_purchased ASC, id DESC
        """,
        (current_user.id,)
    ).fetchall()

    connection.close()

    return render_template(
        "shopping_list.html",
        items=items
    )

@app.route("/shopping-list/bought/<int:item_id>", methods=["POST"])
@login_required
def mark_shopping_item_bought(item_id):
    connection = get_db_connection()

    connection.execute(
        """
        UPDATE shopping_list
        SET is_purchased = 1
        WHERE id = ? AND user_id = ?
        """,
        (item_id, current_user.id)
    )

    connection.commit()
    connection.close()

    return redirect(url_for("shopping_list"))


@app.route("/shopping-list/cancel/<int:item_id>", methods=["POST"])
@login_required
def cancel_shopping_item(item_id):
    connection = get_db_connection()

    connection.execute(
        """
        DELETE FROM shopping_list
        WHERE id = ? AND user_id = ?
        """,
        (item_id, current_user.id)
    )

    connection.commit()
    connection.close()

    return redirect(url_for("shopping_list"))




# ============================================================
# IMAGE UPLOAD SETTINGS
# ============================================================

UPLOAD_FOLDER = os.path.join(
    "static",
    "uploads"
)

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}

app.config[
    "UPLOAD_FOLDER"
] = UPLOAD_FOLDER

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


def allowed_file(filename):

    return (
        "." in filename
        and
        filename.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_EXTENSIONS
    )


# ============================================================
# FOOD IMAGE RECOGNITION
# ============================================================

@app.route(
    "/recognize",
    methods=["GET", "POST"]
)
@login_required
def recognize_food_route():

    if request.method == "POST":

        if "image" not in request.files:

            return render_template(
                "image_upload.html",
                error="Please select an image."
            )

        image = request.files["image"]

        if image.filename == "":

            return render_template(
                "image_upload.html",
                error="Please select an image."
            )

        if not allowed_file(
            image.filename
        ):

            return render_template(
                "image_upload.html",
                error="Invalid image format."
            )

        extension = image.filename.rsplit(
            ".",
            1
        )[1].lower()

        filename = (
            str(uuid.uuid4())
            + "."
            + extension
        )

        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )

        image.save(image_path)

        try:

            result = recognize_food(
                image_path
            )

            prediction = "Unknown Food"

            confidence = None

            if isinstance(result, dict):

                prediction = result.get(
                    "food",
                    result.get(
                        "label",
                        "Unknown Food"
                    )
                )

                confidence = result.get(
                    "confidence"
                )

            elif isinstance(result, tuple):

                if len(result) >= 1:

                    prediction = result[0]

                if len(result) >= 2:

                    confidence = result[1]

            else:

                prediction = result

            return render_template(
                "image_upload.html",
                prediction=prediction,
                confidence=confidence,
                image_path=url_for(
                    "static",
                    filename="uploads/" + filename
                )
            )

        except Exception as error:

            return render_template(
                "image_upload.html",
                error=f"Recognition error: {error}"
            )

    return render_template(
        "image_upload.html"
    )


# ============================================================
# FRESHNESS PREDICTION
# ============================================================
# ============================================================
# FRESHNESS PREDICTION
# ============================================================

@app.route(
    "/freshness",
    methods=["GET", "POST"]
)
@login_required
def freshness():

    if request.method == "POST":

        # ----------------------------------------------------
        # CHECK IMAGE
        # ----------------------------------------------------

        if "image" not in request.files:
            return render_template(
                "freshness.html",
                error="Please select a food image."
            )

        image = request.files["image"]

        if image.filename == "":
            return render_template(
                "freshness.html",
                error="Please select a food image."
            )

        # ----------------------------------------------------
        # CHECK IMAGE FORMAT
        # ----------------------------------------------------

        if not allowed_file(image.filename):
            return render_template(
                "freshness.html",
                error="Please upload JPG, JPEG, PNG or WEBP."
            )

        # ----------------------------------------------------
        # CREATE UNIQUE FILENAME
        # ----------------------------------------------------

        extension = image.filename.rsplit(
            ".",
            1
        )[1].lower()

        filename = (
            str(uuid.uuid4())
            + "."
            + extension
        )

        # ----------------------------------------------------
        # SAVE IMAGE
        # ----------------------------------------------------

        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )

        image.save(image_path)

        try:

            # =================================================
            # 1. FRESHNESS PREDICTION
            # =================================================

            result = predict_freshness(
                image_path
            )

            prediction = (
                "Unable to confidently assess"
            )

            confidence = None

            # ------------------------------------------------
            # HANDLE DICTIONARY RESULT
            # ------------------------------------------------

            if isinstance(result, dict):

                prediction = result.get(
                    "prediction",
                    result.get(
                        "label",
                        result.get(
                            "result",
                            prediction
                        )
                    )
                )

                confidence = result.get(
                    "confidence"
                )

            # ------------------------------------------------
            # HANDLE TUPLE RESULT
            # ------------------------------------------------

            elif isinstance(result, tuple):

                if len(result) >= 1:

                    prediction = result[0]

                if len(result) >= 2:

                    confidence = result[1]

            # ------------------------------------------------
            # HANDLE SIMPLE RESULT
            # ------------------------------------------------

            else:

                prediction = result


            # =================================================
            # 2. CONVERT CONFIDENCE TO PERCENTAGE
            # =================================================

            numeric_confidence = None

            if confidence is not None:

                try:

                    numeric_confidence = float(
                        confidence
                    )

                    # If model returns 0.95,
                    # convert it to 95%.
                    if numeric_confidence <= 1:

                        numeric_confidence *= 100

                except Exception:

                    numeric_confidence = None


            # =================================================
            # 3. LOW CONFIDENCE CHECK
            # =================================================

            if (
                numeric_confidence is not None
                and
                numeric_confidence < 70
            ):

                prediction = (
                    "Unable to confidently assess"
                )


            # =================================================
            # 4. FOOD NAME RECOGNITION
            # =================================================

            food_name = ""

            try:

                food_result = recognize_food(
                    image_path
                )

                # --------------------------------------------
                # If recognize_food() returns a tuple
                # --------------------------------------------

                if isinstance(
                    food_result,
                    tuple
                ):

                    if len(food_result) >= 1:

                        food_name = food_result[0]


                # --------------------------------------------
                # If recognize_food() returns a dictionary
                # --------------------------------------------

                elif isinstance(
                    food_result,
                    dict
                ):

                    food_name = food_result.get(
                        "food",
                        food_result.get(
                            "label",
                            ""
                        )
                    )


                # --------------------------------------------
                # If recognize_food() returns a string
                # --------------------------------------------

                else:

                    food_name = food_result


            except Exception as error:

                print(
                    "Food recognition error:",
                    error
                )

                food_name = ""


            # =================================================
            # 5. SAFETY WARNING
            # =================================================

            warning = (
                "AI/ML visual prediction only. "
                "This does not guarantee that "
                "the food is safe to eat. "
                "Always inspect the food and "
                "consider its expiry date and "
                "storage conditions before consuming."
            )


            # =================================================
            # 6. DISPLAY RESULTS
            # =================================================

            return render_template(
                "freshness.html",

                # Freshness result
                prediction=prediction,

                # Freshness confidence
                confidence=numeric_confidence,

                # Detected food name
                food_name=food_name,

                # Image URL for preview
                image_path=url_for(
                    "static",
                    filename="uploads/" + filename
                ),

                # Actual uploaded filename
                # used when sending image to Add Food
                image_filename=filename,

                # Safety warning
                warning=warning
            )


        except Exception as error:

            return render_template(
                "freshness.html",
                error=(
                    "Freshness prediction error: "
                    + str(error)
                )
            )


    # ========================================================
    # GET REQUEST
    # ========================================================

    return render_template(
        "freshness.html"
    )

# ============================================================
# START APPLICATION
# ============================================================
# EXPIRY DATE OCR
# ============================================================

@app.route("/expiry-ocr", methods=["GET", "POST"])
@login_required
def expiry_ocr():

    if request.method == "POST":

        if "image" not in request.files:

            return render_template(
                "expiry_ocr.html",
                error="Please select a food-package image."
            )

        image = request.files["image"]

        if image.filename == "":

            return render_template(
                "expiry_ocr.html",
                error="Please select a food-package image."
            )

        if not allowed_file(image.filename):

            return render_template(
                "expiry_ocr.html",
                error="Please upload JPG, JPEG, PNG or WEBP."
            )

        extension = image.filename.rsplit(
            ".",
            1
        )[1].lower()

        filename = (
            str(uuid.uuid4())
            + "."
            + extension
        )

        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )

        image.save(image_path)

        try:

            result = detect_expiry_date(
                image_path
            )

            expiry_date = result.get(
                "expiry_date"
            )

            detected_text = result.get(
                "text",
                ""
            )

            # ------------------------------------------------
            # NO DATE FOUND
            # ------------------------------------------------

            if not expiry_date:

                return render_template(
                    "expiry_ocr.html",
                    error=(
                        "No expiry date could be detected. "
                        "Please upload a clearer package image."
                    ),
                    detected_text=detected_text,
                    image_path=url_for(
                        "static",
                        filename="uploads/" + filename
                    )
                )

            # ------------------------------------------------
            # VALIDATE DATE
            # ------------------------------------------------

            parsed_expiry = None

            for date_format in (
                "%d-%m-%Y",
                "%d/%m/%Y",
                "%d.%m.%Y",
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%Y.%m.%d"
            ):

                try:

                    parsed_expiry = datetime.strptime(
                        expiry_date,
                        date_format
                    )

                    break

                except ValueError:

                    continue

            # ------------------------------------------------
            # INVALID DATE
            # ------------------------------------------------

            if parsed_expiry is None:

                return render_template(
                    "expiry_ocr.html",
                    error=(
                        "The detected date could not be "
                        "validated. Please check the package."
                    ),
                    detected_text=detected_text,
                    image_path=url_for(
                        "static",
                        filename="uploads/" + filename
                    )
                )

            # ------------------------------------------------
            # DATABASE DATE
            # ------------------------------------------------

            database_expiry_date = (
                parsed_expiry.strftime(
                    "%Y-%m-%d"
                )
            )
            # ------------------------------------------------
            # RECOGNIZE FOOD
            # ------------------------------------------------

                        # ------------------------------------------------
            # RECOGNIZE FOOD
            # ------------------------------------------------

            food_name = ""

            try:
                food_result = recognize_food(image_path)

                if isinstance(food_result, tuple):
                    if len(food_result) >= 1:
                        food_name = food_result[0]

                elif isinstance(food_result, dict):
                    food_name = food_result.get(
                        "food",
                        food_result.get("label", "")
                    )

                elif isinstance(food_result, str):
                    food_name = food_result

                if food_name in (
                    "Unknown Food",
                    "Food not confidently recognized",
                    "Recognition Failed"
                ):
                    food_name = ""

            except Exception as error:
                print("Food recognition error:", error)
                food_name = ""
            # ------------------------------------------------
            # CHECK DATE STATUS
            # ------------------------------------------------

            if parsed_expiry.date() < date.today():

                date_status = "expired"

            else:

                date_status = "valid"

            # ------------------------------------------------
            # SHOW RESULT
            # ------------------------------------------------

            return render_template(
                "expiry_ocr.html",
                expiry_date=expiry_date,
                database_expiry_date=database_expiry_date,
                date_status=date_status,
                detected_text=detected_text,
                image_path=url_for(
                    "static",
                    filename="uploads/" + filename
                ),
                image_filename=filename,
                food_name=food_name
            )

        except Exception as error:

            return render_template(
                "expiry_ocr.html",
                error=f"OCR error: {error}"
            )

    return render_template(
        "expiry_ocr.html"
    )
# ============================================================
# OPEN BROWSER
# ============================================================

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":
    Timer(
        1.5,
        open_browser
    ).start()

    app.run(
        debug=True
    )