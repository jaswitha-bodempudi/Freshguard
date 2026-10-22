import torch
from torchvision import models
from torchvision.models import ResNet50_Weights
from PIL import Image


# ==========================================
# LOAD PRETRAINED AI MODEL
# ==========================================

weights = ResNet50_Weights.DEFAULT

model = None
preprocess = None
categories = None


def load_food_model():
    global model, preprocess, categories

    if model is None:
        model = models.resnet50(weights=weights)
        model.eval()
        preprocess = weights.transforms()
        categories = weights.meta["categories"]


# ==========================================
# FOOD CATEGORY MAPPING
# ==========================================

FOOD_MAPPING = {

    # Apples
    "granny smith": "Apple",
    "golden delicious": "Apple",
    "apple": "Apple",

    # Banana
    "banana": "Banana",

    # Orange
    "orange": "Orange",

    # Lemon
    "lemon": "Lemon",

    # Strawberry
    "strawberry": "Strawberry",

    # Pineapple
    "pineapple": "Pineapple",

    # Pomegranate
    "pomegranate": "Pomegranate",

    # Tomato
    "tomato": "Tomato",

    # Potato
    "potato": "Potato",

    # Carrot
    "carrot": "Carrot",

    # Broccoli
    "broccoli": "Broccoli",

    # Cauliflower
    "cauliflower": "Cauliflower",

    # Cucumber
    "cucumber": "Cucumber",

    # Mushroom
    "mushroom": "Mushroom",

    # Bread
    "bread": "Bread",

    # Cheese
    "cheese": "Cheese",

    # Egg
    "egg": "Egg",

    # Milk
    "milk": "Milk",

    # Chicken
    "chicken": "Chicken",

    # Fish
    "fish": "Fish",

    # Rice
    "rice": "Rice",

    # Corn
    "corn": "Corn",

    # Bell pepper
    "bell pepper": "Bell Pepper",

    # Cabbage
    "cabbage": "Cabbage",

    # Lettuce
    "head cabbage": "Lettuce"
}


# ==========================================
# CONVERT AI LABEL TO FRESHGUARD FOOD NAME
# ==========================================

def convert_to_food_name(
    ai_label
):

    label = ai_label.lower().strip()

    for keyword, food_name in FOOD_MAPPING.items():

        if keyword in label:

            return food_name

    return None


# ==========================================
# FOOD RECOGNITION FUNCTION
# ==========================================

def recognize_food(
    image_path
):

    try:
        load_food_model()

        # --------------------------------------
        # OPEN IMAGE
        # --------------------------------------

        image = Image.open(
            image_path
        ).convert("RGB")


        # --------------------------------------
        # PREPROCESS IMAGE
        # --------------------------------------

        image_tensor = preprocess(
            image
        )


        # Add batch dimension
        image_tensor = image_tensor.unsqueeze(
            0
        )


        # --------------------------------------
        # AI PREDICTION
        # --------------------------------------

        with torch.no_grad():

            output = model(
                image_tensor
            )


        # --------------------------------------
        # CONVERT TO PROBABILITIES
        # --------------------------------------

        probabilities = torch.nn.functional.softmax(
            output[0],
            dim=0
        )


        # --------------------------------------
        # GET BEST PREDICTION
        # --------------------------------------

        confidence, class_id = torch.max(
            probabilities,
            dim=0
        )


        ai_label = categories[
            class_id.item()
        ]


        confidence_percentage = (
            confidence.item() * 100
        )


        # --------------------------------------
        # CONVERT TO FOOD NAME
        # --------------------------------------

        food_name = convert_to_food_name(
            ai_label
        )


        # --------------------------------------
        # LOW CONFIDENCE CHECK
        # --------------------------------------

        if confidence_percentage < 40:

            return (
                "Food not confidently recognized",
                confidence_percentage
            )


        # --------------------------------------
        # UNKNOWN FOOD CHECK
        # --------------------------------------

        if food_name is None:

            return (
                "Unknown Food",
                confidence_percentage
            )


        # --------------------------------------
        # RETURN RESULT
        # --------------------------------------

        return (
            food_name,
            confidence_percentage
        )


    except Exception as error:

        print(
            "AI recognition error:",
            error
        )

        return (
            "Recognition Failed",
            0
        )