from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import ClassRoom
from .services.course_readme import render_course_readme_html


def _get_readme_classroom_or_response(request, class_id):
    if request.user.role == "teacher":
        classroom = ClassRoom.objects.filter(id=class_id, teacher=request.user).first()
        if classroom:
            return classroom, None
        messages.error(request, "Classroom not found or you do not have access.")
        return None, redirect("teacher_dashboard")

    if request.user.role == "student":
        classroom = ClassRoom.objects.filter(id=class_id, students=request.user).first()
        if classroom:
            return classroom, None
        messages.error(request, "Classroom not found or you do not have access.")
        return None, redirect("student_dashboard")

    messages.error(request, "README access is not available for your current account.")
    return None, redirect("home")


def _get_teacher_classroom_or_response(request, class_id):
    classroom = ClassRoom.objects.filter(id=class_id, teacher=request.user).first()
    if classroom:
        return classroom, None
    messages.error(request, "Classroom not found or you do not have access.")
    return None, redirect("teacher_dashboard")


def _get_base_template(request):
    return "teacher/base.html" if request.user.role == "teacher" else "student/base.html"


@login_required
def course_readme_view(request, id):
    classroom, response = _get_readme_classroom_or_response(request, id)
    if response:
        return response

    context = {
        "classroom": classroom,
        "base_template": _get_base_template(request),
        "readme_html": render_course_readme_html(classroom.readme_content),
        "readme_source": classroom.readme_content or "",
        "can_edit_readme": request.user.role == "teacher" and not getattr(request, "is_mobile", False),
        "is_teacher_view": request.user.role == "teacher",
    }
    return render(request, "course/readme_view.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def course_readme_edit(request, id):
    if request.user.role != "teacher":
        return HttpResponseForbidden("Only teachers can edit course README content.")

    classroom, response = _get_teacher_classroom_or_response(request, id)
    if response:
        return response

    if getattr(request, "is_mobile", False):
        if request.method == "POST":
            return JsonResponse(
                {"ok": False, "error": "README editing is available only on desktop."},
                status=403,
            )

        context = {
            "classroom": classroom,
            "base_template": "teacher/base.html",
            "desktop_only": True,
            "readme_html": render_course_readme_html(classroom.readme_content),
        }
        return render(request, "course/readme_edit.html", context)

    if request.method == "POST":
        readme_content = request.POST.get("readme_content", "")
        classroom.readme_content = readme_content
        classroom.save(update_fields=["readme_content"])
        return JsonResponse(
            {
                "ok": True,
                "message": "README saved successfully.",
                "readme_html": render_course_readme_html(readme_content),
                "updated_at": timezone.localtime(timezone.now()).strftime("%b %d, %Y %I:%M %p"),
            }
        )

    context = {
        "classroom": classroom,
        "base_template": "teacher/base.html",
        "desktop_only": False,
        "readme_html": render_course_readme_html(classroom.readme_content),
        "readme_source": classroom.readme_content or "",
    }
    return render(request, "course/readme_edit.html", context)
