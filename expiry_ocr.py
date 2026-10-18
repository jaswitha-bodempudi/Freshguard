import re
import pytesseract
from PIL import Image


# Tesseract installation location
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def extract_text_from_image(image_path):
    """
    Extract text from a food-package image.
    """

    image = Image.open(image_path)
    image = image.convert("RGB")

    text = pytesseract.image_to_string(
    image,
    config="--psm 6"
)

    return text


def extract_date(text):
    """
    Extract a date in common formats.
    Supports:
    DD-MM-YYYY
    DD/MM/YYYY
    DD.MM.YYYY
    YYYY-MM-DD
    """

    pattern = (
        r"\b(?:"
        r"(?:0?[1-9]|[12][0-9]|3[01])[-/.]"
        r"(?:0?[1-9]|1[0-2])[-/.]"
        r"(?:20\d{2})"
        r"|"
        r"(?:20\d{2})[-/.]"
        r"(?:0?[1-9]|1[0-2])[-/.]"
        r"(?:0?[1-9]|[12][0-9]|3[01])"
        r")\b"
    )

    match = re.search(pattern, text)

    if match:
        return match.group(0)

    return None


def find_expiry_date(text):
    """
    Find expiry date by giving priority to text
    containing expiry-related keywords.

    Examples:
    EXP DATE : 29-09-2026
    EXPIRY DATE : 29/09/2026
    USE BY : 29-09-2026
    BEST BEFORE : 29-09-2026
    """

    # Normalize OCR text
    normalized_text = text.replace("\n", " ")

    # Expiry-related keywords
    expiry_keywords = [
        "exp",
        "expiry",
        "expires",
        "use by",
        "best before",
        "valid till",
        "valid upto",
        "valid up to"
    ]

    # First priority:
    # Look for an expiry keyword followed by a date.
    for keyword in expiry_keywords:

        pattern = (
            re.escape(keyword)
            + r"[^0-9]{0,30}"
            + r"("
            r"(?:0?[1-9]|[12][0-9]|3[01])[-/.]"
            r"(?:0?[1-9]|1[0-2])[-/.]"
            r"(?:20\d{2})"
            r"|"
            r"(?:20\d{2})[-/.]"
            r"(?:0?[1-9]|1[0-2])[-/.]"
            r"(?:0?[1-9]|[12][0-9]|3[01])"
            r")"
        )

        match = re.search(
            pattern,
            normalized_text,
            re.IGNORECASE
        )

        if match:
            return match.group(1)

    # Second priority:
    # Check line-by-line because OCR often keeps
    # "Exp. Date : 29-09-2026" on one line.

    lines = text.splitlines()

    for line in lines:

        lower_line = line.lower()

        if any(
            keyword in lower_line
            for keyword in expiry_keywords
        ):

            date = extract_date(line)

            if date:
                return date

    # Final fallback:
    # If there is no expiry keyword, return the first date.
    return extract_date(text)


def detect_expiry_date(image_path):

    text = extract_text_from_image(image_path)

    expiry_date = find_expiry_date(text)

    return {
        "text": text,
        "expiry_date": expiry_date
    }