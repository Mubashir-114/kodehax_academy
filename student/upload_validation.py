from pathlib import Path

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


MAX_ASSIGNMENT_FILE_SIZE = 10 * 1024 * 1024
MAX_PROFILE_IMAGE_SIZE = 3 * 1024 * 1024

ALLOWED_ASSIGNMENT_EXTENSIONS = {
    ".c",
    ".cpp",
    ".csv",
    ".doc",
    ".docx",
    ".java",
    ".js",
    ".md",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".py",
    ".txt",
    ".xls",
    ".xlsx",
    ".zip",
}
ALLOWED_PROFILE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_PROFILE_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _extension(uploaded_file):
    return Path(uploaded_file.name or "").suffix.lower()


def validate_assignment_upload(uploaded_file):
    if uploaded_file.size > MAX_ASSIGNMENT_FILE_SIZE:
        raise ValidationError("Assignment files must be 10MB or smaller.")
    if _extension(uploaded_file) not in ALLOWED_ASSIGNMENT_EXTENSIONS:
        raise ValidationError("Unsupported assignment file type.")


def validate_profile_image(uploaded_file):
    if uploaded_file.size > MAX_PROFILE_IMAGE_SIZE:
        raise ValidationError("Profile images must be 3MB or smaller.")
    if _extension(uploaded_file) not in ALLOWED_PROFILE_IMAGE_EXTENSIONS:
        raise ValidationError("Use a JPG, PNG, or WebP profile image.")
    content_type = getattr(uploaded_file, "content_type", "")
    if content_type and content_type not in ALLOWED_PROFILE_IMAGE_CONTENT_TYPES:
        raise ValidationError("Use a valid JPG, PNG, or WebP profile image.")

    current_position = uploaded_file.tell()
    try:
        image = Image.open(uploaded_file)
        image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("The uploaded profile image is invalid.") from exc
    finally:
        uploaded_file.seek(current_position)
