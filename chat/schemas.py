"""Validate provider JSON before existing UI normalization or score calculation."""
import json
import math


CHAT_SCHEMA = {
    "type": str, "title": str, "content": str, "examples": list,
    "quiz": list, "follow_up": list, "difficulty": str, "tags": list,
}
VISION_SCHEMA = {
    "type": str, "detected_content": str, "explanation": str,
    "steps": list, "solution": str, "mistakes": list, "follow_up": list,
}
RUBRIC_SCHEMA = {
    "syntax": (int, float), "logic": (int, float),
    "structure": (int, float), "readability": (int, float), "summary": str,
}


def validate_json(text, schema=None):
    def reject_constant(value):
        raise ValueError("Non-finite JSON number")

    payload = json.loads(text, parse_constant=reject_constant)
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Expected a nonempty JSON object")
    for key, kind in (schema or {}).items():
        value = payload.get(key)
        if not isinstance(value, kind) or isinstance(value, bool):
            raise ValueError("Invalid JSON field: " + key)
        if isinstance(value, (int, float)) and not math.isfinite(value):
            raise ValueError("Non-finite JSON number")
        if isinstance(value, list):
            if key == "quiz":
                for item in value:
                    if not isinstance(item, dict):
                        raise ValueError("Invalid quiz item")
                    for field in ("level", "question", "answer", "explanation"):
                        if not isinstance(item.get(field), str):
                            raise ValueError("Invalid quiz field")
                    options = item.get("options")
                    if not isinstance(options, list) or any(not isinstance(x, str) for x in options):
                        raise ValueError("Invalid quiz options")
            elif any(not isinstance(item, str) for item in value):
                raise ValueError("Invalid JSON string list")
    return payload
