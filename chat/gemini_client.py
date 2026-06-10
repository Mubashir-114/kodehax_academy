from __future__ import annotations

from functools import lru_cache

from google import genai

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


AI_ISSUE_CACHE_KEY = "ai_service_last_issue"
AI_ISSUE_CACHE_TTL_SECONDS = 60 * 60 * 24


class GeminiServiceError(Exception):
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


def _missing_key_error() -> GeminiServiceError:
    return GeminiServiceError(
        "missing_key",
        "AI key is not connected",
        "The assistant is ready, but the Gemini API key is missing or not loaded.",
        "Add GEMINI_API_KEY to .env and restart the Django server.",
        status_code=503,
    )


def normalize_gemini_exception(exc: Exception) -> GeminiServiceError:
    if isinstance(exc, GeminiServiceError):
        record_ai_service_issue(exc)
        return exc

    detail = str(exc).lower()
    exc_name = type(exc).__name__.lower()

    if any(token in detail for token in ("api key", "apikey", "unauthorized", "permission denied", "401", "403")):
        error = GeminiServiceError(
            "auth",
            "AI access needs attention",
            "The Gemini key was rejected or does not have permission for this request.",
            "Check that GEMINI_API_KEY is valid and enabled for the selected Gemini model.",
            status_code=503,
        )
        record_ai_service_issue(error)
        return error

    if any(token in detail for token in ("quota", "rate limit", "resource_exhausted", "too many requests", "429")):
        error = GeminiServiceError(
            "quota",
            "AI limit reached",
            "The AI service is taking a breather because the current quota or rate limit was reached.",
            "Wait a little while, reduce request volume, or upgrade the Gemini quota for this key.",
            status_code=429,
        )
        record_ai_service_issue(error)
        return error

    if any(token in detail or token in exc_name for token in ("timeout", "deadline", "temporarily unavailable", "503", "unavailable")):
        error = GeminiServiceError(
            "unavailable",
            "AI is temporarily unavailable",
            "The request reached Gemini, but the service did not respond in time.",
            "Try again in a moment. Your page and work are still safe.",
            status_code=503,
        )
        record_ai_service_issue(error)
        return error

    error = GeminiServiceError(
        "unknown",
        "AI response could not be completed",
        "Something interrupted the AI request before a useful answer came back.",
        "Try again, or check the server logs if this keeps happening.",
        status_code=503,
    )
    record_ai_service_issue(error)
    return error


def record_ai_service_issue(error: GeminiServiceError) -> None:
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
    error = normalize_gemini_exception(exc)
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
    error = normalize_gemini_exception(exc)
    return {
        "code": error.code,
        "title": error.title,
        "message": error.message,
        "suggestion": error.suggestion,
        "status_code": error.status_code,
    }


def get_ai_service_status() -> dict[str, str | bool | None]:
    cached_issue = cache.get(AI_ISSUE_CACHE_KEY)
    if not settings.GEMINI_API_KEY:
        return {
            "ok": False,
            "code": "missing_key",
            "title": "AI key is not connected",
            "message": "GEMINI_API_KEY is missing or empty in the active environment.",
            "suggestion": "Add a valid GEMINI_API_KEY to .env, then restart the Django server.",
            "last_seen": timezone.now().isoformat(),
        }
    if cached_issue:
        return {"ok": False, **cached_issue}
    return {
        "ok": True,
        "code": "configured",
        "title": "AI service configured",
        "message": "GEMINI_API_KEY is present. No recent AI service issue has been recorded.",
        "suggestion": "",
        "last_seen": None,
    }


@lru_cache(maxsize=1)
def get_gemini_client():
    if not settings.GEMINI_API_KEY:
        raise _missing_key_error()
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def generate_text(model: str, prompt: str, config=None) -> str:
    try:
        response = get_gemini_client().models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        return getattr(response, "text", "") or ""
    except Exception as exc:  # noqa: BLE001
        raise normalize_gemini_exception(exc) from exc


def generate_multimodal(model: str, contents, config=None) -> str:
    try:
        response = get_gemini_client().models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        return getattr(response, "text", "") or ""
    except Exception as exc:  # noqa: BLE001
        raise normalize_gemini_exception(exc) from exc


def list_model_names() -> list[str]:
    names = []
    for model in get_gemini_client().models.list():
        model_name = getattr(model, "name", "")
        if model_name:
            names.append(model_name)
    return names


def list_generate_content_models() -> list[str]:
    names = []
    for model in get_gemini_client().models.list():
        model_name = getattr(model, "name", "")
        supported = set(getattr(model, "supported_actions", []) or [])
        methods = set(getattr(model, "supported_generation_methods", []) or [])
        if model_name and ("generateContent" in methods or "generateContent" in supported):
            names.append(model_name)
    return names
