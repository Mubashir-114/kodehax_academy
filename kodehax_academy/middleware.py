from __future__ import annotations

import re


_MOBILE_UA_PATTERN = re.compile(
    r"(android|iphone|ipod|ipad|blackberry|iemobile|opera mini|mobile)",
    re.IGNORECASE,
)


class DeviceDetectionMiddleware:
    """
    Adds request.is_mobile based on UA + client hints + viewport cookie override.
    """

    SESSION_OVERRIDE_KEY = "force_mobile_view"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.is_mobile = self._is_mobile_request(request)
        response = self.get_response(request)
        return response

    def _is_mobile_request(self, request):
        forced_param = request.GET.get("mobile")
        if forced_param in {"1", "true", "yes"}:
            request.session[self.SESSION_OVERRIDE_KEY] = True
            return True
        if forced_param in {"0", "false", "no"}:
            request.session[self.SESSION_OVERRIDE_KEY] = False
            return False

        if self.SESSION_OVERRIDE_KEY in request.session:
            return bool(request.session.get(self.SESSION_OVERRIDE_KEY))

        ch_mobile = (request.headers.get("Sec-CH-UA-Mobile") or "").strip().lower()
        if ch_mobile == "?1":
            return True
        if ch_mobile == "?0":
            return False

        viewport_hint = (request.COOKIES.get("viewport_bucket") or "").strip().lower()
        if viewport_hint == "mobile":
            return True
        if viewport_hint == "desktop":
            return False

        user_agent = request.META.get("HTTP_USER_AGENT", "")
        return bool(_MOBILE_UA_PATTERN.search(user_agent))
