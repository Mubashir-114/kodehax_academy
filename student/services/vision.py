from __future__ import annotations

import json
import re
import ast
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from chat.ai_service import ai_error_payload, generate_image
from chat.schemas import VISION_SCHEMA

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", re.IGNORECASE)

VISION_PROMPT = """
You are an AI learning assistant with vision capability.

Analyze the uploaded image and classify it into:
- code
- math
- exam
- diagram
- notes

Then respond in valid JSON:
{
  "type": "",
  "detected_content": "",
  "explanation": "",
  "steps": [],
  "solution": "",
  "mistakes": [],
  "follow_up": []
}

Rules:
- If code -> debug and fix errors
- If math -> solve step-by-step
- If exam -> answer all questions
- If diagram -> explain clearly
- If notes -> summarize
- Keep the response precise, structured, and student-friendly.
- If the image is unclear, say so in explanation and suggest a clearer image in follow_up.
- Return JSON only with no markdown wrapper.
""".strip()


class ImageQueryError(Exception):
    def __init__(self, message: str, suggestion: str = "Try a clearer image.") -> None:
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion


def _safe_json_load(raw_text: str) -> dict[str, Any]:
    if not raw_text:
        return {}
    raw_text = raw_text.strip()
    try:
        parsed = json.loads(raw_text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    block_match = JSON_BLOCK_PATTERN.search(raw_text)
    if block_match:
        try:
            parsed = json.loads(block_match.group(1))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass

    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(raw_text[start : end + 1])
    except json.JSONDecodeError:
        candidate = raw_text[start : end + 1]
        candidate = re.sub(r"\btrue\b", "True", candidate)
        candidate = re.sub(r"\bfalse\b", "False", candidate)
        candidate = re.sub(r"\bnull\b", "None", candidate)
        try:
            parsed = ast.literal_eval(candidate)
        except (SyntaxError, ValueError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _coerce_string_list(value: Any, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=True)
        text = text.strip()
        if text:
            items.append(text)
    return items[:limit]


def _normalize_response(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "type": str(payload.get("type", "notes")).strip().lower() or "notes",
        "detected_content": str(payload.get("detected_content", "")).strip(),
        "explanation": str(payload.get("explanation", "")).strip(),
        "steps": _coerce_string_list(payload.get("steps", []), limit=8),
        "solution": str(payload.get("solution", "")).strip(),
        "mistakes": _coerce_string_list(payload.get("mistakes", []), limit=8),
        "follow_up": _coerce_string_list(payload.get("follow_up", []), limit=6),
    }
    if normalized["type"] not in {"code", "math", "exam", "diagram", "notes"}:
        normalized["type"] = "notes"
    if not normalized["follow_up"]:
        normalized["follow_up"] = [
            "Upload a clearer image if any text looks wrong.",
            "Ask for a simpler explanation.",
            "Try a related practice question.",
        ]
    return normalized


def validate_uploaded_image(uploaded_file) -> None:
    if not uploaded_file:
        raise ImageQueryError("No image was uploaded.", "Upload a JPG or PNG image.")
    extension = Path(uploaded_file.name or "").suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ImageQueryError("Unsupported image type.", "Use a JPG or PNG image.")
    if uploaded_file.size > MAX_IMAGE_SIZE_BYTES:
        raise ImageQueryError("Image exceeds the 5MB limit.", "Upload a smaller image.")


def upload_image_to_ai(uploaded_file) -> dict[str, Any]:
    validate_uploaded_image(uploaded_file)
    try:
        with Image.open(uploaded_file) as source:
            image = source.convert("RGB")
            image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageQueryError("The uploaded file is not a valid image.", "Try a clearer JPG or PNG image.") from exc
    finally:
        uploaded_file.seek(0)

    try:
        response = generate_image(VISION_PROMPT, image, schema=VISION_SCHEMA)
        return process_response(response)
    except ImageQueryError:
        raise
    except Exception as exc:
        error = ai_error_payload(exc)
        raise ImageQueryError(error["title"], error["suggestion"]) from exc
    finally:
        image.close()
        uploaded_file.seek(0)


def process_response(raw_text: str) -> dict[str, Any]:
    parsed = _safe_json_load(raw_text)
    if not parsed:
        raise ImageQueryError("The AI could not understand the image response.", "Try a clearer image.")
    normalized = _normalize_response(parsed)
    if not normalized["explanation"] and not normalized["solution"]:
        raise ImageQueryError("The image content was unclear.", "Try a clearer image.")
    return normalized
