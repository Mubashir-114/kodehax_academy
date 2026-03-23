import socket
from smtplib import SMTPException
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.utils import DatabaseError, OperationalError, ProgrammingError
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from accounts.forms import TeacherInvitationAdminForm, resend_teacher_invitation
from accounts.models import TeacherInvitation
from daily_challenges.models import DailyChallenge, StudentChallengeAttempt, StudentPoints
from teacher.models import (
    Assignment,
    CodeSubmission,
    PerformanceRecord,
    QuizAnswer,
    Submission,
)
from teacher.services.performance import get_admin_analytics_page, get_admin_dashboard_analytics
from kodehax_academy.mobile import render_for_device

from .decorators import admin_required
from .models import AdminUserState, PlatformSettings, SiteSettings

User = get_user_model()


def _render_admin(request, template_name, context):
    base_context = {
        "current_section": context.get("current_section", "dashboard"),
    }
    base_context.update(context)
    return render(request, template_name, base_context)


def _to_json(value):
    return value


def _seven_day_labels(today):
    return [
        (today - timedelta(days=offset)).strftime("%d %b")
        for offset in range(6, -1, -1)
    ]


def _build_daily_map(queryset, date_key="day", value_key="total"):
    return {entry[date_key]: entry[value_key] for entry in queryset}


@admin_required
def admin_entry(request):
    return redirect("adminpanel_dashboard")


@admin_required
def dashboard(request):
    recent_users = User.objects.order_by("-date_joined")[:8]
    recent_assignments = Assignment.objects.select_related(
        "classroom",
        "classroom__teacher",
    ).order_by("-created_at")[:8]
    analytics = get_admin_dashboard_analytics()

    context = {
        "current_section": "dashboard",
        "analytics": analytics,
        "recent_users": recent_users,
        "recent_assignments": recent_assignments,
    }
    return _render_admin(request, "adminpanel/dashboard.html", context)


@admin_required
def users(request):
    query = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "").strip()
    status_filter = request.GET.get("status", "").strip()
    page_number = request.GET.get("page")
    activity_user_id = request.GET.get("activity_user")
    edit_user_id = request.GET.get("edit_user")

    user_qs = User.objects.all().order_by("-date_joined")

    if query:
        user_qs = user_qs.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
        )
    if role_filter:
        user_qs = user_qs.filter(role=role_filter)
    if status_filter == "active":
        user_qs = user_qs.filter(is_active=True)
    elif status_filter == "suspended":
        user_qs = user_qs.filter(is_active=False)

    paginator = Paginator(user_qs, 15)
    page_obj = paginator.get_page(page_number)

    selected_activity_user = None
    selected_activity_records = []
    if activity_user_id:
        selected_activity_user = User.objects.filter(id=activity_user_id).first()
        if selected_activity_user:
            selected_activity_records = (
                PerformanceRecord.objects.select_related("assignment", "classroom")
                .filter(student=selected_activity_user)
                .order_by("-recorded_at")[:6]
            )

    selected_edit_user = None
    if edit_user_id:
        selected_edit_user = User.objects.filter(id=edit_user_id).first()

    context = {
        "current_section": "users",
        "page_obj": page_obj,
        "query": query,
        "role_filter": role_filter,
        "status_filter": status_filter,
        "selected_activity_user": selected_activity_user,
        "selected_activity_records": selected_activity_records,
        "selected_edit_user": selected_edit_user,
    }
    return _render_admin(request, "adminpanel/users.html", context)


@admin_required
def user_action(request, user_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    target_user = get_object_or_404(User, id=user_id)
    action = request.POST.get("action", "").strip()

    if target_user == request.user and action in {"suspend", "delete"}:
        messages.error(request, "You cannot suspend or delete your own account.")
        return redirect("adminpanel_users")

    state, _ = AdminUserState.objects.get_or_create(user=target_user)

    if action == "suspend":
        target_user.is_active = False
        target_user.save(update_fields=["is_active"])
        state.suspended_at = timezone.now()
        state.suspension_reason = request.POST.get(
            "reason",
            "Suspended by administrator",
        )
        state.save(update_fields=["suspended_at", "suspension_reason", "updated_at"])
        messages.success(request, f"{target_user.username} suspended.")
    elif action == "activate":
        target_user.is_active = True
        target_user.save(update_fields=["is_active"])
        state.suspended_at = None
        state.suspension_reason = ""
        state.save(update_fields=["suspended_at", "suspension_reason", "updated_at"])
        messages.success(request, f"{target_user.username} activated.")
    elif action == "delete":
        username = target_user.username
        target_user.delete()
        messages.success(request, f"{username} deleted.")
    elif action == "promote_teacher":
        target_user.role = "teacher"
        target_user.save(update_fields=["role"])
        state.teacher_approval_status = AdminUserState.STATUS_PENDING
        state.save(update_fields=["teacher_approval_status", "updated_at"])
        messages.success(request, f"{target_user.username} promoted to teacher.")
    else:
        messages.error(request, "Unsupported action.")

    return redirect("adminpanel_users")


@admin_required
def user_edit(request, user_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    target_user = get_object_or_404(User, id=user_id)
    target_user.email = request.POST.get("email", target_user.email).strip()

    requested_role = request.POST.get("role", target_user.role).strip()
    if requested_role in {"student", "teacher", "admin"}:
        target_user.role = requested_role

    target_user.is_active = request.POST.get("is_active") == "on"
    target_user.save(update_fields=["email", "role", "is_active"])
    messages.success(request, f"{target_user.username} updated successfully.")
    return redirect("adminpanel_users")


@admin_required
def teachers(request):
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    page_number = request.GET.get("page")

    teacher_qs = (
        User.objects.filter(role="teacher")
        .select_related("teacher_profile", "adminpanel_state")
        .annotate(
            classes_count=Count("teacher_classes", distinct=True),
            assignments_count=Count("teacher_classes__assignments", distinct=True),
        )
        .order_by("-date_joined")
    )

    if query:
        teacher_qs = teacher_qs.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
        )
    if status_filter:
        teacher_qs = teacher_qs.filter(
            adminpanel_state__teacher_approval_status=status_filter
        )

    paginator = Paginator(teacher_qs, 12)
    page_obj = paginator.get_page(page_number)
    for teacher in page_obj:
        try:
            teacher.approval_status = teacher.adminpanel_state.teacher_approval_status
        except AdminUserState.DoesNotExist:
            teacher.approval_status = AdminUserState.STATUS_PENDING

    context = {
        "current_section": "teachers",
        "page_obj": page_obj,
        "query": query,
        "status_filter": status_filter,
        "invitation_form": TeacherInvitationAdminForm(),
        "pending_invitations": TeacherInvitation.objects.filter(is_used=False)[:10],
    }
    return _render_admin(request, "adminpanel/teachers.html", context)


@admin_required
def invite_teacher(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    form = TeacherInvitationAdminForm(request.POST)
    if form.is_valid():
        try:
            invitation = form.save(request=request)
        except (SMTPException, TimeoutError, OSError, socket.timeout) as exc:
            messages.error(
                request,
                "Invitation email could not be sent. Check SMTP settings, network access, and the sender credentials.",
            )
            messages.error(request, f"Mail error: {exc}")
        else:
            action = "Invitation sent" if getattr(invitation, "was_created", False) else "Invitation re-sent"
            messages.success(request, f"{action} to {invitation.email}.")
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
    return redirect("adminpanel_teachers")


@admin_required
def resend_teacher_invite(request, invitation_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    invitation = get_object_or_404(TeacherInvitation, id=invitation_id)
    try:
        resend_teacher_invitation(request, invitation)
    except (SMTPException, TimeoutError, OSError, socket.timeout) as exc:
        messages.error(
            request,
            "Invitation email could not be re-sent. Check SMTP settings, network access, and the sender credentials.",
        )
        messages.error(request, f"Mail error: {exc}")
    else:
        messages.success(request, f"Invitation re-sent to {invitation.email}.")
    return redirect("adminpanel_teachers")


@admin_required
def delete_teacher_invite(request, invitation_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    invitation = get_object_or_404(TeacherInvitation, id=invitation_id)
    invitation_email = invitation.email
    invitation.delete()
    messages.success(request, f"Invitation data deleted for {invitation_email}.")
    return redirect("adminpanel_teachers")


@admin_required
def teacher_action(request, teacher_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    teacher_user = get_object_or_404(User, id=teacher_id, role="teacher")
    action = request.POST.get("action", "").strip()
    state, _ = AdminUserState.objects.get_or_create(user=teacher_user)

    if action == "approve":
        state.teacher_approval_status = AdminUserState.STATUS_APPROVED
        teacher_user.is_active = True
        teacher_user.save(update_fields=["is_active"])
        state.save(update_fields=["teacher_approval_status", "updated_at"])
        messages.success(request, f"{teacher_user.username} approved.")
    elif action == "reject":
        state.teacher_approval_status = AdminUserState.STATUS_REJECTED
        teacher_user.is_active = False
        teacher_user.save(update_fields=["is_active"])
        state.save(update_fields=["teacher_approval_status", "updated_at"])
        messages.success(request, f"{teacher_user.username} rejected.")
    elif action == "remove":
        username = teacher_user.username
        teacher_user.delete()
        messages.success(request, f"{username} removed.")
    else:
        messages.error(request, "Unsupported action.")

    return redirect("adminpanel_teachers")


@admin_required
def students(request):
    query = request.GET.get("q", "").strip()
    page_number = request.GET.get("page")

    student_qs = (
        User.objects.filter(role="student")
        .select_related()
        .annotate(
            classes_count=Count("enrolled_classes", distinct=True),
            submissions_count=Count("performance_records", distinct=True),
            average_score=Avg("performance_records__score"),
        )
        .order_by("-date_joined")
    )

    if query:
        student_qs = student_qs.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
        )

    paginator = Paginator(student_qs, 12)
    page_obj = paginator.get_page(page_number)

    context = {
        "current_section": "students",
        "page_obj": page_obj,
        "query": query,
    }
    return _render_admin(request, "adminpanel/students.html", context)


@admin_required
def student_action(request, student_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    student_user = get_object_or_404(User, id=student_id, role="student")
    action = request.POST.get("action", "").strip()

    if action == "remove":
        username = student_user.username
        student_user.delete()
        messages.success(request, f"{username} removed.")
    elif action == "suspend":
        student_user.is_active = False
        student_user.save(update_fields=["is_active"])
        state, _ = AdminUserState.objects.get_or_create(user=student_user)
        state.suspended_at = timezone.now()
        state.suspension_reason = "Suspended by administrator"
        state.save(update_fields=["suspended_at", "suspension_reason", "updated_at"])
        messages.success(request, f"{student_user.username} suspended.")
    else:
        messages.error(request, "Unsupported action.")

    return redirect("adminpanel_students")


@admin_required
def assignments(request):
    query = request.GET.get("q", "").strip()
    low_completion_only = request.GET.get("low_completion") == "1"
    page_number = request.GET.get("page")

    assignment_qs = (
        Assignment.objects.select_related("classroom", "classroom__teacher")
        .annotate(
            enrolled_students=Count("classroom__students", distinct=True),
            file_submission_count=Count("submissions", distinct=True),
            code_submission_count=Count("code_submissions", distinct=True),
            quiz_submission_count=Count("quiz_questions__answers__student", distinct=True),
        )
        .order_by("-created_at")
    )

    if query:
        assignment_qs = assignment_qs.filter(
            Q(title__icontains=query)
            | Q(classroom__name__icontains=query)
            | Q(classroom__teacher__username__icontains=query)
        )

    assignment_rows = []
    for assignment in assignment_qs:
        total_submissions = (
            assignment.file_submission_count
            + assignment.code_submission_count
            + assignment.quiz_submission_count
        )
        completion_rate = (
            round((total_submissions / assignment.enrolled_students) * 100, 2)
            if assignment.enrolled_students
            else 0
        )
        is_low_completion = completion_rate < 50
        if low_completion_only and not is_low_completion:
            continue
        assignment_rows.append(
            {
                "assignment": assignment,
                "total_submissions": total_submissions,
                "completion_rate": completion_rate,
                "is_low_completion": is_low_completion,
            }
        )

    paginator = Paginator(assignment_rows, 12)
    page_obj = paginator.get_page(page_number)

    context = {
        "current_section": "assignments",
        "page_obj": page_obj,
        "query": query,
        "low_completion_only": low_completion_only,
    }
    return _render_admin(request, "adminpanel/assignments.html", context)


@admin_required
def assignment_action(request, assignment_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    assignment = get_object_or_404(Assignment, id=assignment_id)
    action = request.POST.get("action", "").strip()
    if action == "delete":
        title = assignment.title
        assignment.delete()
        messages.success(request, f"Assignment '{title}' deleted.")
    else:
        messages.error(request, "Unsupported action.")
    return redirect("adminpanel_assignments")


@admin_required
def analytics(request):
    context = {
        "current_section": "analytics",
        "analytics": get_admin_analytics_page(),
    }
    return _render_admin(request, "adminpanel/analytics.html", context)


@admin_required
def settings_view(request):
    from .forms import PlatformSettingsForm

    platform_settings = PlatformSettings.load()
    maintenance_mode_enabled = False
    try:
        site_settings = SiteSettings.load()
        maintenance_mode_enabled = site_settings.maintenance_mode
    except (DatabaseError, OperationalError, ProgrammingError):
        site_settings = None
        messages.warning(
            request,
            "Site settings table is not ready yet. Run migrations to enable maintenance mode control.",
        )
    
    if request.method == "POST":
        form = PlatformSettingsForm(request.POST, instance=platform_settings)
        if form.is_valid():
            form.save()
            messages.success(request, "Platform settings updated successfully.")
            return redirect("adminpanel_settings")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PlatformSettingsForm(instance=platform_settings)

    context = {
        "current_section": "settings",
        "form": form,
        "maintenance_mode_enabled": maintenance_mode_enabled,
    }
    return _render_admin(request, "adminpanel/settings.html", context)


def maintenance_page(request):
    response = render_for_device(request, "maintenance.html")
    response.status_code = 503
    response["Retry-After"] = "600"
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@admin_required
@require_POST
def toggle_maintenance_mode(request):
    enabled = request.POST.get("maintenance_mode") == "true"
    try:
        site_settings = SiteSettings.load()
        was_enabled = site_settings.maintenance_mode
        site_settings.maintenance_mode = enabled

        # When maintenance ends, invalidate app user sessions created before this point.
        if was_enabled and not enabled:
            site_settings.force_logout_generation += 1
            site_settings.save(
                update_fields=["maintenance_mode", "force_logout_generation", "updated_at"]
            )
        else:
            site_settings.save(update_fields=["maintenance_mode", "updated_at"])
    except (DatabaseError, OperationalError, ProgrammingError):
        return JsonResponse(
            {
                "success": False,
                "maintenance_mode": False,
                "message": "Site settings table is unavailable. Run migrations first.",
            },
            status=503,
        )

    # Keep existing platform settings value in sync for backward compatibility.
    platform_settings = PlatformSettings.load()
    if platform_settings.maintenance_mode != enabled:
        platform_settings.maintenance_mode = enabled
        platform_settings.save(update_fields=["maintenance_mode"])

    return JsonResponse(
        {
            "success": True,
            "maintenance_mode": enabled,
            "message": "Maintenance mode updated successfully.",
        }
    )


