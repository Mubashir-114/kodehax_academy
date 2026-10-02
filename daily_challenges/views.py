from code_execution.service import ExecutionUnavailable
from datetime import timedelta
import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from adminpanel.decorators import admin_required
from kodehax_academy.mobile import render_for_device

from .forms import QuestionTemplateCSVImportForm, QuestionTemplateForm
from .models import DailyChallenge, DailyChallengeSession, QuestionTemplate, StudentPoints
from .services import (
    challenge_attempt_limit,
    challenge_dashboard_stats,
    can_access_challenge,
    get_today_challenge_set,
    level_unlock_state,
    preview_solution,
    regenerate_daily_challenges,
    refresh_challenge_set,
    submit_solution_for_challenge,
    unlock_hint,
    _get_level_totals,
    _calculate_completion_threshold,
)

User = get_user_model()

def _format_remaining_time(seconds):
    total = max(int(seconds), 0)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _ensure_student(request):
    if request.user.role != "student":
        messages.error(request, "Only students can access daily coding challenges.")
        return redirect("home")
    return None


def _challenge_groups(challenge_set):
    unlocks = level_unlock_state(challenge_set)
    level_totals = _get_level_totals(challenge_set)
    
    labels = {
        1: ("Level 1", "Easy"),
        2: ("Level 2", "Medium"),
        3: ("Level 3", "Hard"),
    }
    items = []
    ordered = list(challenge_set.challenges.select_related("problem").order_by("level", "question_number", "id"))
    
    # Calculate thresholds for each level
    easy_threshold = _calculate_completion_threshold(level_totals[1])
    medium_threshold = _calculate_completion_threshold(level_totals[2])
    
    for level in (1, 2, 3):
        if unlocks[level]:
            required_text = "Available now"
        else:
            if level == 2:
                required_text = f"Unlock after completing 75% of Easy questions ({easy_threshold}/{level_totals[1]} solved)"
            else:  # level == 3
                required_text = f"Unlock after completing 75% of Medium questions ({medium_threshold}/{level_totals[2]} solved)"
        
        items.append(
            {
                "level": level,
                "title": labels[level][0],
                "difficulty": labels[level][1],
                "unlocked": unlocks[level],
                "required_text": required_text,
                "challenges": [challenge for challenge in ordered if challenge.level == level],
            }
        )
    return items


def _challenge_set_summary(challenge_set):
    challenges = list(challenge_set.challenges.all())
    easy_total = sum(1 for challenge in challenges if challenge.level == 1)
    medium_total = sum(1 for challenge in challenges if challenge.level == 2)
    hard_total = sum(1 for challenge in challenges if challenge.level == 3)
    return {
        "total_challenges": len(challenges),
        "max_score": sum(challenge.points for challenge in challenges),
        "easy_total": easy_total,
        "medium_total": medium_total,
        "hard_total": hard_total,
    }


def _workspace_navigation(challenge_set, current_challenge):
    ordered = list(challenge_set.challenges.order_by("level", "question_number", "id"))
    previous_item = None
    next_item = None
    for index, item in enumerate(ordered):
        if item.id != current_challenge.id:
            continue
        if index > 0:
            previous_item = ordered[index - 1]
        if index + 1 < len(ordered):
            next_item = ordered[index + 1]
        break
    return previous_item, next_item


def _next_accessible_challenge(challenge_set, current_challenge):
    ordered = list(challenge_set.challenges.order_by("level", "question_number", "id"))
    current_index = None
    for index, item in enumerate(ordered):
        if item.id == current_challenge.id:
            current_index = index
            break
    if current_index is None:
        return None

    for item in ordered[current_index + 1:]:
        if can_access_challenge(item):
            return item
    return None


def _workspace_nav_items(challenge_set, current_challenge):
    unlocks = level_unlock_state(challenge_set)
    return [
        {
            "challenge": item,
            "current": item.id == current_challenge.id,
            "unlocked": unlocks.get(item.level, False),
        }
        for item in challenge_set.challenges.order_by("level", "question_number", "id")
    ]


def _remaining_workspace_challenges(challenge_set, current_challenge):
    ordered = list(challenge_set.challenges.order_by("level", "question_number", "id"))
    remaining = 0
    current_seen = False

    for item in ordered:
        if item.id == current_challenge.id:
            current_seen = True
        if not current_seen:
            continue
        if item.status != DailyChallenge.STATUS_SOLVED:
            remaining += 1

    return remaining


def _build_workspace_editor_code(challenge):
    return ""


@login_required
def today_challenges(request):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    challenge_set = get_today_challenge_set(request.user)
    refresh_challenge_set(challenge_set)
    challenge_set.refresh_from_db()
    challenge_set = (
        challenge_set.__class__.objects.filter(id=challenge_set.id)
        .prefetch_related("challenges__problem")
        .get()
    )
    
    # Ensure all challenges have valid JSON fields
    for challenge in challenge_set.challenges.all():
        if not isinstance(challenge.test_cases, list):
            challenge.test_cases = []
        if not isinstance(challenge.generated_parameters, dict):
            challenge.generated_parameters = {}
        if not isinstance(challenge.latest_result, dict):
            challenge.latest_result = {}
    
    remaining_time = max(challenge_set.expires_at - timezone.now(), timedelta(0))
    remaining_time_seconds = int(remaining_time.total_seconds())

    points, _ = StudentPoints.objects.get_or_create(student=request.user)
    current_session = DailyChallengeSession.objects.filter(
        student=request.user,
        date=challenge_set.date,
    ).first()
    
    # Ensure session has valid JSON fields
    if current_session:
        if not isinstance(current_session.attempted_challenge_ids, list):
            current_session.attempted_challenge_ids = []

    return render_for_device(
        request,
        "daily_challenges/today.html",
        {
            "challenge_set": challenge_set,
            "remaining_time": remaining_time,
            "remaining_time_seconds": remaining_time_seconds,
            "remaining_time_label": _format_remaining_time(remaining_time_seconds),
            "challenge_groups": _challenge_groups(challenge_set),
            **_challenge_set_summary(challenge_set),
            "level_unlocks": level_unlock_state(challenge_set),
            "student_points": points,
            "current_session": current_session,
        },
    )


@login_required
def submit_solution(request, challenge_id):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    try:
        challenge = DailyChallenge.objects.select_related("student", "problem", "challenge_set").get(id=challenge_id)
    except DailyChallenge.DoesNotExist:
        messages.error(request, "This challenge does not exist.")
        return redirect("daily_challenges_today")
    
    if challenge.student != request.user:
        messages.error(request, "You do not have permission to access this challenge.")
        return redirect("daily_challenges_today")
    refresh_challenge_set(challenge.challenge_set)
    if not can_access_challenge(challenge):
        messages.error(request, "This level is locked. Solve the required earlier questions first.")
        return redirect("daily_challenges_today")

    response_status = 200
    preview_payload = None
    submission_payload = None
    editor_code = _build_workspace_editor_code(challenge)

    if request.method == "POST":
        action = request.POST.get("action", "submit")

        if action == "hint":
            hint_payload = unlock_hint(challenge)
            if not hint_payload["ok"]:
                messages.error(request, hint_payload["error"])
            else:
                messages.success(request, f"Hint {hint_payload['hints_used']} unlocked.")
            return redirect("daily_challenge_workspace", challenge_id=challenge.id)

        code = request.POST.get("code", "").rstrip()
        editor_code = code or editor_code

        if not code:
            messages.error(request, "Code cannot be empty.")
            return redirect("daily_challenge_workspace", challenge_id=challenge.id)

        if action == "run":
            try:
                preview_payload = preview_solution(challenge, code)
            except ExecutionUnavailable as exc:
                response_status = 503
                preview_payload = {"allowed": False, "error": str(exc), "results": [], "summary": {}}
            if not preview_payload["allowed"]:
                messages.error(request, preview_payload["error"])
            else:
                messages.success(request, "Test run completed.")
        elif action == "submit":
            try:
                submission_payload = submit_solution_for_challenge(challenge, code)
            except ExecutionUnavailable as exc:
                response_status = 503
                submission_payload = {"ok": False, "error": str(exc)}
            if not submission_payload["ok"]:
                messages.error(request, submission_payload["error"])
            else:
                success_message = submission_payload["message"]
                if submission_payload["solved"]:
                    success_message = (
                        f"{success_message} "
                        f"Question score: +{submission_payload['final_score']}. "
                        f"Daily score: {submission_payload['challenge_set'].total_score}."
                    )
                messages.success(request, success_message)
                challenge.refresh_from_db()
                challenge.challenge_set.refresh_from_db()
                if submission_payload["solved"]:
                    next_challenge = _next_accessible_challenge(challenge.challenge_set, challenge)
                    if next_challenge is not None:
                        return redirect("daily_challenge_workspace", challenge_id=next_challenge.id)
                    return redirect("daily_challenges_today")
        else:
            return HttpResponseBadRequest("Invalid action.")

    challenge.refresh_from_db()
    refresh_challenge_set(challenge.challenge_set)
    challenge.challenge_set.refresh_from_db()
    remaining_time = max(challenge.challenge_set.expires_at - timezone.now(), timedelta(0))
    remaining_time_seconds = int(remaining_time.total_seconds())
    previous_challenge, next_challenge = _workspace_navigation(challenge.challenge_set, challenge)
    unlocks = level_unlock_state(challenge.challenge_set)

    return render_for_device(
        request,
        "daily_challenges/workspace.html",
        {
            "challenge": challenge,
            "challenge_set": challenge.challenge_set,
            "remaining_time": remaining_time,
            "remaining_time_seconds": remaining_time_seconds,
            "remaining_time_label": _format_remaining_time(remaining_time_seconds),
            "preview_payload": preview_payload,
            "submission_payload": submission_payload,
            "editor_code": editor_code,
            "level_unlocks": unlocks,
            "challenge_groups": _challenge_groups(challenge.challenge_set),
            **_challenge_set_summary(challenge.challenge_set),
            "previous_challenge": previous_challenge,
            "next_challenge": next_challenge,
            "next_challenge_unlocked": bool(next_challenge and unlocks.get(next_challenge.level, False)),
            "workspace_nav_items": _workspace_nav_items(challenge.challenge_set, challenge),
            "visible_hints": [hint for hint in (challenge.hint1, challenge.hint2)[: challenge.hints_used] if hint],
            "attempt_limit": challenge_attempt_limit(challenge),
            "attempts_remaining": max(0, challenge_attempt_limit(challenge) - challenge.attempts),
            "student_points": StudentPoints.objects.get_or_create(student=request.user)[0],
            "current_session": DailyChallengeSession.objects.filter(
                student=request.user,
                date=challenge.challenge_set.date,
            ).first(),
            "remaining_challenges": _remaining_workspace_challenges(challenge.challenge_set, challenge),
        },
        status=response_status,
    )


@admin_required
def adminpanel_daily_challenges(request):
    stats = challenge_dashboard_stats()
    csv_form = QuestionTemplateCSVImportForm()
    return render(
        request,
        "adminpanel/daily_challenges.html",
        {
            "current_section": "daily_challenges",
            "csv_form": csv_form,
            **stats,
        },
    )


@admin_required
def adminpanel_regenerate_daily_challenges(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    student_id = request.POST.get("student_id")
    if student_id:
        student = get_object_or_404(User, id=student_id, role="student")
        regenerate_daily_challenges(student=student)
        messages.success(request, f"Daily challenges regenerated for {student.username}.")
    else:
        regenerate_daily_challenges()
        messages.success(request, "Daily challenges regenerated for all students.")
    return redirect("adminpanel_daily_challenges")


@admin_required
def adminpanel_import_question_templates(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    form = QuestionTemplateCSVImportForm(request.POST, request.FILES)
    if not form.is_valid():
        for error_list in form.errors.values():
            for error in error_list:
                messages.error(request, error)
        return redirect("adminpanel_daily_challenges")

    created_count = 0
    for row in form.parse_rows():
        title = (row.get("title_template") or "").strip()
        description = (row.get("description_template") or title).strip()
        difficulty = (row.get("difficulty") or QuestionTemplate.DIFFICULTY_EASY).strip().lower()
        topic = (row.get("topic") or "general").strip().lower()
        param_name = (row.get("param_name") or "").strip()
        param_values = [item.strip() for item in (row.get("param_values") or "").split(",") if item.strip()]
        test_cases_raw = (row.get("test_cases_template") or "").strip()
        if not title:
            continue
        parameter_schema = {param_name: param_values} if param_name and param_values else {}
        parsed_test_cases = []
        if test_cases_raw:
            try:
                parsed_test_cases = json.loads(test_cases_raw)
            except json.JSONDecodeError:
                parsed_test_cases = []
        auto_approve = bool(parsed_test_cases)
        QuestionTemplate.objects.create(
            title_template=title,
            description_template=description,
            difficulty=difficulty,
            topic=topic,
            parameter_schema=parameter_schema,
            starter_code_template=(row.get("starter_code_template") or "").strip(),
            function_name=(row.get("function_name") or "solve").strip(),
            hint1_template=(row.get("hint1_template") or "").strip(),
            hint2_template=(row.get("hint2_template") or "").strip(),
            approval_status=QuestionTemplate.STATUS_APPROVED if auto_approve else QuestionTemplate.STATUS_PENDING,
            approved_by=request.user if auto_approve else None,
            approved_at=timezone.now() if auto_approve else None,
            created_by=request.user,
            is_active=auto_approve,
            approval_note="" if auto_approve else "Imported without test cases; add test_cases_template JSON and approve before use.",
            test_cases_template=parsed_test_cases,
        )
        created_count += 1

    messages.success(request, f"Imported {created_count} question templates.")
    return redirect("adminpanel_daily_challenges")


@admin_required
def adminpanel_review_question_template(request, template_id):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    template = get_object_or_404(QuestionTemplate, id=template_id)
    action = request.POST.get("action", "").strip()
    note = request.POST.get("approval_note", "").strip()
    if action == "approve":
        template.approval_status = QuestionTemplate.STATUS_APPROVED
        template.approved_by = request.user
        template.approved_at = timezone.now()
        template.is_active = True
        template.approval_note = note
        template.save(update_fields=["approval_status", "approved_by", "approved_at", "is_active", "approval_note", "updated_at"])
        messages.success(request, f"Approved template '{template.title_template}'.")
    elif action == "reject":
        template.approval_status = QuestionTemplate.STATUS_REJECTED
        template.approved_by = request.user
        template.approved_at = timezone.now()
        template.is_active = False
        template.approval_note = note
        template.save(update_fields=["approval_status", "approved_by", "approved_at", "is_active", "approval_note", "updated_at"])
        messages.success(request, f"Rejected template '{template.title_template}'.")
    else:
        messages.error(request, "Unsupported action.")
    return redirect("adminpanel_daily_challenges")


@login_required
def teacher_submit_question_template(request):
    if request.user.role != "teacher":
        messages.error(request, "Only teachers can submit question templates.")
        return redirect("home")

    if request.method == "POST":
        form = QuestionTemplateForm(request.POST)
        if form.is_valid():
            template = form.save(commit=False)
            template.created_by = request.user
            template.approval_status = QuestionTemplate.STATUS_PENDING
            template.is_active = False
            template.save()
            messages.success(request, "Template submitted for admin approval.")
            return redirect("teacher_dashboard")
    else:
        form = QuestionTemplateForm()

    my_templates = QuestionTemplate.objects.filter(created_by=request.user).order_by("-created_at")[:10]
    return render(
        request,
        "teacher/question_template_form.html",
        {
            "form": form,
            "my_templates": my_templates,
        },
    )
