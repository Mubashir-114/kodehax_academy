from __future__ import annotations

import base64
from io import BytesIO

from groq import Groq
from .schemas import validate_json

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


AI_ISSUE_CACHE_KEY = "groq_service_last_issue"
AI_ISSUE_CACHE_TTL_SECONDS = 60 * 60 * 24


class AIServiceError(Exception):
    def __init__(
        self,
        code: str,
        title: str,
        message: str,
        suggestion: str,
        status_code: int = 503,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.title = title
        self.message = message
        self.suggestion = suggestion
        self.status_code = status_code


def _missing_key_error() -> AIServiceError:
    return AIServiceError(
        "missing_key",
        "AI key is not connected",
        "The assistant is ready, but the Groq API key is missing or not loaded.",
        "Add GROQ_API_KEY to .env and restart the Django server.",
        status_code=503,
    )


def normalize_ai_exception(exc: Exception) -> AIServiceError:
    if isinstance(exc, AIServiceError):
        record_ai_service_issue(exc)
        return exc

    status = getattr(exc, "status_code", None)
    detail = str(status or "").lower()
    exc_name = type(exc).__name__.lower()

    if status in (401, 403) or any(token in detail for token in ("api key", "apikey", "unauthorized", "permission denied", "401", "403")):
        error = AIServiceError(
            "auth",
            "AI access needs attention",
            "The Groq key was rejected or does not have permission for this request.",
            "Check that GROQ_API_KEY is valid and enabled for the selected Groq model.",
            status_code=503,
        )
        record_ai_service_issue(error)
        return error

    if status == 429 or any(token in detail for token in ("quota", "rate limit", "resource_exhausted", "too many requests", "429")):
        error = AIServiceError(
            "quota",
            "AI limit reached",
            "The AI service is taking a breather because the current quota or rate limit was reached.",
            "Wait a little while, reduce request volume, or upgrade the Groq quota for this key.",
            status_code=429,
        )
        record_ai_service_issue(error)
        return error

    if status in (408, 500, 502, 503, 504) or any(token in exc_name for token in ("timeout", "connection")):
        error = AIServiceError(
            "unavailable",
            "AI is temporarily unavailable",
            "The AI service could not be reached or did not respond in time.",
            "Try again in a moment. Your page and work are still safe.",
            status_code=503,
        )
        record_ai_service_issue(error)
        return error

    if status == 400:
        error = AIServiceError(
            "invalid_request", "AI request could not be accepted",
            "Groq rejected the request format, image, or model parameters.",
            "Check the configured model and supported image/request limits.",
            status_code=503,
        )
        record_ai_service_issue(error)
        return error

    error = AIServiceError(
        "unknown",
        "AI response could not be completed",
        "Something interrupted the AI request before a useful answer came back.",
        "Try again, or check the server logs if this keeps happening.",
        status_code=503,
    )
    record_ai_service_issue(error)
    return error


def record_ai_service_issue(error: AIServiceError) -> None:
    cache.set(
        AI_ISSUE_CACHE_KEY,
        {
            "code": error.code,
            "title": error.title,
            "message": error.message,
            "suggestion": error.suggestion,
            "status_code": error.status_code,
            "last_seen": timezone.now().isoformat(),
        },
        timeout=AI_ISSUE_CACHE_TTL_SECONDS,
    )


def ai_error_payload(exc: Exception) -> dict[str, str]:
    error = normalize_ai_exception(exc)
    if error.code == "quota":
        code = "service_busy"
        title = "AI service is busy"
        message = "The AI service could not complete this request right now."
        suggestion = "Please try again later. The platform team can see the service details."
    else:
        code = "service_unavailable"
        title = "AI service is temporarily unavailable"
        message = "The assistant is online, but the AI service could not complete this request."
        suggestion = "Please try again later. The platform team can see the service details."
    return {
        "code": code,
        "title": title,
        "message": message,
        "suggestion": suggestion,
    }


def ai_admin_error_payload(exc: Exception) -> dict[str, str]:
    error = normalize_ai_exception(exc)
    return {
        "code": error.code,
        "title": error.title,
        "message": error.message,
        "suggestion": error.suggestion,
        "status_code": error.status_code,
    }


def get_ai_service_status() -> dict[str, str | bool | None]:
    cached_issue = cache.get(AI_ISSUE_CACHE_KEY)
    if not settings.GROQ_API_KEY:
        return {
            "ok": False,
            "code": "missing_key",
            "title": "AI key is not connected",
            "message": "GROQ_API_KEY is missing or empty in the active environment.",
            "suggestion": "Add a valid GROQ_API_KEY to .env, then restart the Django server.",
            "last_seen": timezone.now().isoformat(),
        }
    if cached_issue:
        return {"ok": False, **cached_issue}
    return {
        "ok": True,
        "code": "configured",
        "title": "AI service configured",
        "message": "GROQ_API_KEY is present. No recent issue is recorded; account access is not checked by this status.",
        "suggestion": "",
        "last_seen": None,
    }


def get_groq_client():
    if not settings.GROQ_API_KEY:
        raise _missing_key_error()
    # Bound request time and avoid SDK retries multiplying interactive latency.
    return Groq(api_key=settings.GROQ_API_KEY, timeout=30.0, max_retries=0)


def _complete(model, messages, *, json_mode=False, schema=None, vision=False):
    try:
        kwargs = {
            "model": model, "messages": messages,
            "max_completion_tokens": 4096, "stream": False,
        }
        if vision:
            # Qwen defaults to thinking. Instruct mode keeps JSON in content.
            kwargs["reasoning_effort"] = "none"
        if json_mode or schema:
            kwargs["response_format"] = {"type": "json_object"}
        with get_groq_client() as client:
            response = client.chat.completions.create(**kwargs)
        if not response.choices or response.choices[0].finish_reason != "stop":
            raise AIServiceError("malformed_output", "AI response was incomplete",
                                 "The provider returned a truncated or unusable response.",
                                 "Try again with a smaller request.")
        text = response.choices[0].message.content
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Empty provider content")
        if json_mode or schema:
            validate_json(text, schema)
        cache.delete(AI_ISSUE_CACHE_KEY)
        return text
    except (ValueError, TypeError, AttributeError, IndexError) as exc:
        error = AIServiceError("malformed_output", "AI response could not be read",
                               "The provider returned an invalid response format.",
                               "Please retry the request.")
        record_ai_service_issue(error)
        raise error from exc
    except Exception as exc:
        raise normalize_ai_exception(exc) from exc


def generate_text(prompt: str, *, json_mode=False, schema=None) -> str:
    return _complete(settings.GROQ_TEXT_MODEL, [{"role": "user", "content": prompt}],
                     json_mode=json_mode, schema=schema)


def generate_image(prompt, image, *, schema=None):
    # Re-encode validated pixels: no filenames, EXIF, or user URLs leave the server.
    encoded = BytesIO()
    image.save(encoded, format="JPEG")
    data = encoded.getvalue()
    if len(data) > 10 * 1024 * 1024:
        raise AIServiceError("invalid_image", "Image is too large for AI analysis",
                             "The decoded image exceeds the request size limit.",
                             "Upload a smaller image.")
    url = "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")
    return _complete(settings.GROQ_VISION_MODEL, [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": url}},
    ]}], json_mode=True, schema=schema, vision=True)


def list_model_names():
    try:
        with get_groq_client() as client:
            return [model.id for model in client.models.list().data]
    except Exception as exc:
        raise normalize_ai_exception(exc) from exc
