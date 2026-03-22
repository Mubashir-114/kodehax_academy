from django.contrib import messages
from django.contrib.auth import logout
from django.conf import settings
from django.db.utils import DatabaseError, OperationalError, ProgrammingError
from django.shortcuts import redirect
from django.urls import reverse

from .models import SiteSettings


class MaintenanceModeMiddleware:
    SESSION_FORCE_LOGOUT_KEY = "force_logout_generation"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        maintenance_path = reverse("maintenance_page")

        # Allow operational/admin and asset routes while maintenance mode is active.
        allowed_prefixes = (
            "/admin/",
            "/admin-panel/",
            settings.STATIC_URL,
            settings.MEDIA_URL,
        )
        if path.startswith(allowed_prefixes):
            return self.get_response(request)

        try:
            site_settings = SiteSettings.load()
        except (DatabaseError, OperationalError, ProgrammingError):
            return self.get_response(request)

        # Keep the maintenance endpoint accessible only while maintenance mode is active.
        if path == maintenance_path:
            if site_settings.maintenance_mode:
                return self.get_response(request)
            return redirect("home")

        user = getattr(request, "user", None)

        # Superusers can bypass maintenance mode to perform interventions.
        if user and user.is_authenticated and user.is_superuser:
            return self.get_response(request)

        # Force-logout app users once maintenance turns OFF.
        if user and user.is_authenticated and not site_settings.maintenance_mode:
            user_role = getattr(user, "role", "")
            if user_role in {"student", "teacher"}:
                session_generation = request.session.get(self.SESSION_FORCE_LOGOUT_KEY)
                current_generation = site_settings.force_logout_generation

                if session_generation is None:
                    # Existing sessions from before this feature rollout are invalidated when generation > 0.
                    if current_generation > 0:
                        logout(request)
                        messages.info(
                            request,
                            "You were signed out because maintenance has completed. Please sign in again.",
                        )
                        return redirect("home")
                    request.session[self.SESSION_FORCE_LOGOUT_KEY] = current_generation
                elif session_generation < current_generation:
                    logout(request)
                    messages.info(
                        request,
                        "You were signed out because maintenance has completed. Please sign in again.",
                    )
                    return redirect("home")

            return self.get_response(request)

        if not site_settings.maintenance_mode:
            return self.get_response(request)

        return redirect("maintenance_page")
