import os
import shutil
import random

SOURCE_DIR = "dataset"
OUTPUT_DIR = "freshness_data"

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

TRAIN_RATIO = 0.8

random.seed(42)


def collect_images(folder):
    images = []

    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.lower().endswith(IMAGE_EXTENSIONS):
                images.append(os.path.join(root, file))

    return images


def get_label(path):
    path_lower = path.lower()

    if "fresh" in path_lower:
        return "fresh"

    if "rotten" in path_lower:
        return "rotten"

    return None


def main():

    fresh_images = []
    rotten_images = []

    all_images = collect_images(SOURCE_DIR)

    for image_path in all_images:

        label = get_label(image_path)

        if label == "fresh":
            fresh_images.append(image_path)

        elif label == "rotten":
            rotten_images.append(image_path)

    print("Fresh images found:", len(fresh_images))
    print("Rotten images found:", len(rotten_images))

    if len(fresh_images) == 0 or len(rotten_images) == 0:
        print("\nERROR: Could not find fresh/rotten folders.")
        print("Check the dataset folder structure.")
        return

    output_folders = [
        os.path.join(OUTPUT_DIR, "train", "fresh"),
        os.path.join(OUTPUT_DIR, "train", "rotten"),
        os.path.join(OUTPUT_DIR, "test", "fresh"),
        os.path.join(OUTPUT_DIR, "test", "rotten")
    ]

    for folder in output_folders:
        os.makedirs(folder, exist_ok=True)

    def split_and_copy(images, label):

        random.shuffle(images)

        split_index = int(len(images) * TRAIN_RATIO)

        train_images = images[:split_index]
        test_images = images[split_index:]

        for i, image_path in enumerate(train_images):
            extension = os.path.splitext(image_path)[1]
            destination = os.path.join(
                OUTPUT_DIR,
                "train",
                label,
                f"{label}_train_{i}{extension}"
            )
            shutil.copy2(image_path, destination)

        for i, image_path in enumerate(test_images):
            extension = os.path.splitext(image_path)[1]
            destination = os.path.join(
                OUTPUT_DIR,
                "test",
                label,
                f"{label}_test_{i}{extension}"
            )
            shutil.copy2(image_path, destination)

    split_and_copy(fresh_images, "fresh")
    split_and_copy(rotten_images, "rotten")

    print("\nDataset preparation completed!")

    print("\nFinal structure:")
    print("freshness_data/")
    print("├── train/")
    print("│   ├── fresh/")
    print("│   └── rotten/")
    print("└── test/")
    print("    ├── fresh/")
    print("    └── rotten/")


if __name__ == "__main__":
    main()