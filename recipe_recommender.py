
RECIPES = [
    {
        "name": "Banana Oatmeal",
        "ingredients": ["banana", "oats", "milk"],
        "instructions": "Mix oats and milk, cook until soft, and add sliced banana."
    },
    {
        "name": "Vegetable Fried Rice",
        "ingredients": ["rice", "carrot", "peas", "onion"],
        "instructions": "Cook the vegetables, add cooked rice, and stir-fry until hot."
    },
    {
        "name": "Tomato Cheese Sandwich",
        "ingredients": ["bread", "tomato", "cheese"],
        "instructions": "Place sliced tomato and cheese between bread and toast."
    },
    {
        "name": "Banana Smoothie",
        "ingredients": ["banana", "milk"],
        "instructions": "Blend banana and milk until smooth."
    },
    {
        "name": "Vegetable Omelette",
        "ingredients": ["egg", "onion", "tomato"],
        "instructions": "Beat the eggs, mix in chopped vegetables, and cook thoroughly."
    },
    {
        "name": "Carrot Rice",
        "ingredients": ["rice", "carrot", "onion"],
        "instructions": "Cook the vegetables, add cooked rice, and mix well."
    }
]


def recommend_recipes(food_items):
    """
    Recommend recipes based on food names in the inventory.
    food_items should be a list of food-name strings.
    """

    available_foods = {
        item.strip().lower()
        for item in food_items
        if item and item.strip()
    }

    recommendations = []

    for recipe in RECIPES:
        matched = [
            ingredient
            for ingredient in recipe["ingredients"]
            if ingredient in available_foods
        ]

        if matched:
            missing = [
                ingredient
                for ingredient in recipe["ingredients"]
                if ingredient not in available_foods
            ]

            recommendations.append({
                "name": recipe["name"],
                "matched_ingredients": matched,
                "missing_ingredients": missing,
                "instructions": recipe["instructions"],
                "match_count": len(matched),
                "total_ingredients": len(recipe["ingredients"])
            })

    recommendations.sort(
        key=lambda recipe: recipe["match_count"],
        reverse=True
    )

    return recommendations
