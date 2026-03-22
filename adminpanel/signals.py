from django.contrib.auth.signals import user_logged_in
from django.db.utils import DatabaseError, OperationalError, ProgrammingError
from django.dispatch import receiver

from .models import SiteSettings


@receiver(user_logged_in)
def sync_session_force_logout_generation(sender, request, user, **kwargs):
    if request is None:
        return
    try:
        settings_obj = SiteSettings.load()
    except (DatabaseError, OperationalError, ProgrammingError):
        return
    request.session["force_logout_generation"] = settings_obj.force_logout_generation
