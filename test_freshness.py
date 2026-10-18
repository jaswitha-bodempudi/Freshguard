from freshness_model import predict_freshness


image_path = "test_image.jpg"

result = predict_freshness(image_path)

print("\nFreshGuard Freshness Result")
print("----------------------------")

print("Status:", result["status"])
print("Confidence:", f"{result['confidence']:.2f}%")

print("\nWARNING:")
print(
    "AI/ML visual prediction only. "
    "This does not guarantee that the food is safe to eat."
)