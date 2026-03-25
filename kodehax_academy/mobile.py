from __future__ import annotations

from django.conf import settings
from django.shortcuts import render
from django.template import TemplateDoesNotExist
from django.template.loader import get_template


MOBILE_TEMPLATE_MAP = {
    "user/base.html": "mobile/home.html",
    "user/login/std_login.html": "mobile/auth/login.html",
    "accounts/register.html": "mobile/auth/register.html",
    "accounts/verify_login_otp.html": "mobile/auth/verify_otp.html",
    "accounts/forgot_password.html": "mobile/auth/forgot_password.html",
    "accounts/reset_password.html": "mobile/auth/reset_password.html",
    "accounts/registration_success.html": "mobile/auth/registration_success.html",
    "student/dashboard.html": "mobile/student/dashboard.html",
    "student/class_detail.html": "mobile/student/course_detail.html",
    "student/assignment/view_assignment.html": "mobile/student/courses.html",
    "student/assignment/submit_assignment.html": "mobile/student/lesson.html",
    "student/assignment/submit_code.html": "mobile/student/lesson_code.html",
    "student/assignment/take_quiz.html": "mobile/student/quiz.html",
    "student/profile.html": "mobile/student/profile.html",
    "student/update.html": "mobile/student/profile_edit.html",
    "student/performance.html": "mobile/student/notifications.html",
    "daily_challenges/today.html": "mobile/daily_challenges/today.html",
    "daily_challenges/workspace.html": "mobile/daily_challenges/workspace.html",
    "maintenance.html": "mobile/maintenance.html",
}


def _resolve_mobile_template(desktop_template_name, explicit_mobile_template=None):
    # Keep one consistent UI/theme across desktop and mobile by default.
    if getattr(settings, "FORCE_DESKTOP_UI_ON_MOBILE", True):
        return None

    candidate = explicit_mobile_template or MOBILE_TEMPLATE_MAP.get(desktop_template_name)
    if not candidate:
        return None
    try:
        get_template(candidate)
    except TemplateDoesNotExist:
        return None
    return candidate


def render_for_device(
    request,
    desktop_template_name,
    context=None,
    status=200,
    mobile_template_name=None,
):
    template_name = desktop_template_name
    if getattr(request, "is_mobile", False):
        mobile_candidate = _resolve_mobile_template(desktop_template_name, mobile_template_name)
        if mobile_candidate:
            template_name = mobile_candidate

    payload = context.copy() if isinstance(context, dict) else {}
    payload.setdefault("is_mobile", bool(getattr(request, "is_mobile", False)))
    return render(request, template_name, payload, status=status)
