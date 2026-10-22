import torch
from torchvision import transforms, models
from PIL import Image


DEVICE = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu"
)

MODEL_PATH = "models/freshness_model.pth"


# -----------------------------
# LOAD MODEL
# -----------------------------

classes = None
model = None


def load_freshness_model():
    global classes, model

    if model is None:
        checkpoint = torch.load(
            MODEL_PATH,
            map_location=DEVICE
        )

        classes = checkpoint["classes"]

        loaded_model = models.resnet50(weights=None)
        loaded_model.fc = torch.nn.Linear(
            loaded_model.fc.in_features,
            2
        )

        loaded_model.load_state_dict(
            checkpoint["model_state_dict"]
        )

        loaded_model = loaded_model.to(DEVICE)
        loaded_model.eval()

        model = loaded_model

# -----------------------------
# IMAGE TRANSFORMATION
# -----------------------------

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        [0.485, 0.456, 0.406],
        [0.229, 0.224, 0.225]
    )
])


# -----------------------------
# PREDICT FRESHNESS
# -----------------------------

def predict_freshness(image_path):
    load_freshness_model()

    image = Image.open(image_path).convert("RGB")

    image_tensor = transform(image)

    image_tensor = image_tensor.unsqueeze(0)

    image_tensor = image_tensor.to(DEVICE)

    with torch.no_grad():

        outputs = model(image_tensor)

        probabilities = torch.softmax(
            outputs,
            dim=1
        )

        confidence, predicted = torch.max(
            probabilities,
            1
        )

    confidence = confidence.item() * 100

    predicted_class = classes[predicted.item()]

    # Don't make a low-confidence claim
    if confidence < 70:
        return {
            "status": "Unable to confidently assess",
            "confidence": confidence
        }

    if predicted_class.lower() == "fresh":

        return {
            "status": "Looks Fresh",
            "confidence": confidence
        }

    return {
        "status": "Possible Spoilage",
        "confidence": confidence
    }
