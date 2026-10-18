from expiry_ocr import detect_expiry_date


image_path = "milk_expiry.jpg"


result = detect_expiry_date(image_path)


print("\nFreshGuard OCR Result")
print("---------------------")

print("\nDetected Text:")
print(result["text"])


print("\nDetected Expiry Date:")

if result["expiry_date"]:
    print(result["expiry_date"])
else:
    print("No expiry date detected.")