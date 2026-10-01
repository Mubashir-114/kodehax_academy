from code_execution.service import ExecutionUnavailable
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from adminpanel.decorators import admin_required
from daily_challenges.models import DailyChallengeSet

from .forms import CodingAssessmentForm, MCQAssessmentForm, SelfAssessmentForm
from .models import AssessmentQuestion, CodingProblem, StudentAssessment, StudentSkill
from .services import (
    calculate_self_assessment_score,
    ensure_default_assessment_content,
    evaluate_coding_responses,
    evaluate_mcq_responses,
    finalize_assessment,
    reset_student_assessment,
)

User = get_user_model()


def _ensure_student(request):
    if request.user.role != "student":
        messages.error(request, "Only students can access the skill evaluation.")
        return redirect("home")
    return None


def _get_student_assessment(student):
    return StudentAssessment.objects.get_or_create(student=student)[0]


def _build_daily_heatmap(student, window_days=42):
    today = timezone.localdate()
    start_date = today - timedelta(days=window_days - 1)
    challenge_sets = DailyChallengeSet.objects.filter(
        student=student,
        date__range=(start_date, today),
    ).values("date", "solved_count")

    solved_by_date = {row["date"]: int(row["solved_count"] or 0) for row in challenge_sets}
    dates = [start_date + timedelta(days=offset) for offset in range(window_days)]
    total_solved = 0
    active_days = 0
    best_day = None
    cells = []
    for day in dates:
        solved = solved_by_date.get(day, 0)
        total_solved += solved
        if solved > 0:
            active_days += 1
            if not best_day or solved > best_day["count"]:
                best_day = {"date": day, "count": solved}
        if solved == 0:
            level = 0
        elif solved <= 2:
            level = 1
        elif solved <= 4:
            level = 2
        elif solved <= 6:
            level = 3
        else:
            level = 4
        cells.append({"date": day, "count": solved, "level": level})

    heatmap_weeks = [cells[index : index + 7] for index in range(0, len(cells), 7)]
    consistency = int(round((active_days / window_days) * 100)) if window_days else 0
    return {
        "weeks": heatmap_weeks,
        "summary": {
            "active_days": active_days,
            "consistency": consistency,
            "total_solved": total_solved,
            "best_day": best_day,
            "window_days": window_days,
        },
    }


@login_required
def assessment_entry(request):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    ensure_default_assessment_content()
    assessment = _get_student_assessment(request.user)
    if assessment.completed:
        return redirect("skill_assessment_profile")
    return redirect("skill_assessment_step", step=assessment.current_step or 1)


@login_required
def assessment_step(request, step):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    ensure_default_assessment_content()
    assessment = _get_student_assessment(request.user)
    if assessment.completed:
        messages.info(request, "Your skill evaluation has already been completed.")
        return redirect("skill_assessment_profile")

    step = max(1, min(int(step), 3))
    if step > assessment.current_step:
        return redirect("skill_assessment_step", step=assessment.current_step)

    questions = list(
        AssessmentQuestion.objects.filter(is_active=True).order_by("order", "id")[:10]
    )
    problems = list(
        CodingProblem.objects.filter(is_active=True).order_by("order", "id")[:2]
    )

    if step == 1:
        initial = assessment.self_assessment_answers or None
        form = SelfAssessmentForm(request.POST or None, initial=initial)
        if request.method == "POST" and form.is_valid():
            score = calculate_self_assessment_score(form.cleaned_data)
            assessment.self_assessment_answers = form.cleaned_data
            assessment.self_assessment_score = score
            assessment.current_step = 2
            assessment.save(
                update_fields=[
                    "self_assessment_answers",
                    "self_assessment_score",
                    "current_step",
                    "updated_at",
                ]
            )
            return redirect("skill_assessment_step", step=2)
    elif step == 2:
        initial = assessment.mcq_answers or None
        form = MCQAssessmentForm(request.POST or None, initial=initial, questions=questions)
        if request.method == "POST" and form.is_valid():
            result = evaluate_mcq_responses(questions, form.cleaned_data)
            assessment.mcq_answers = result["answers"]
            assessment.mcq_score = int(result["normalized_score"])
            assessment.mcq_breakdown = result["topic_breakdown"]
            assessment.current_step = 3
            assessment.save(
                update_fields=[
                    "mcq_answers",
                    "mcq_score",
                    "mcq_breakdown",
                    "current_step",
                    "updated_at",
                ]
            )
            return redirect("skill_assessment_step", step=3)
    else:
        initial = {}
        for problem in problems:
            initial[f"problem_{problem.id}"] = assessment.coding_answers.get(
                str(problem.id),
                problem.starter_code,
            )
        form = CodingAssessmentForm(request.POST or None, initial=initial, problems=problems)
        if request.method == "POST" and form.is_valid():
            try:
                result = evaluate_coding_responses(problems, form.cleaned_data)
            except ExecutionUnavailable as exc:
                form.add_error(None, str(exc))
                return render(request, "skill_assessment/assessment_form.html", {
                    "assessment": assessment, "form": form, "questions": questions,
                    "problems": problems, "step": step, "step_percent": 100, "total_steps": 3,
                }, status=503)
            assessment.coding_answers = result["answers"]
            assessment.coding_score = int(result["normalized_score"])
            assessment.coding_breakdown = result["breakdown"]
            assessment.save(
                update_fields=[
                    "coding_answers",
                    "coding_score",
                    "coding_breakdown",
                    "updated_at",
                ]
            )
            finalize_assessment(assessment)
            messages.success(request, "Skill evaluation completed successfully.")
            return redirect("skill_assessment_complete")

    context = {
        "assessment": assessment,
        "form": form,
        "questions": questions,
        "problems": problems,
        "step": step,
        "step_percent": int((step / 3) * 100),
        "total_steps": 3,
    }
    return render(request, "skill_assessment/assessment_form.html", context)


@login_required
def assessment_complete(request):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    skill_profile = StudentSkill.objects.filter(student=request.user).first()
    assessment = StudentAssessment.objects.filter(student=request.user).first()
    if not skill_profile or not assessment or not assessment.completed:
        return redirect("skill_assessment_entry")

    return render(
        request,
        "skill_assessment/assessment_complete.html",
        {
            "skill_profile": skill_profile,
            "assessment": assessment,
            "medium_topics": skill_profile.assessment_snapshot.get("medium_topics", []),
        },
    )


@login_required
def assessment_profile(request):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    skill_profile = StudentSkill.objects.filter(student=request.user).first()
    assessment = StudentAssessment.objects.filter(student=request.user).first()
    if not skill_profile or not assessment or not assessment.completed:
        return redirect("skill_assessment_entry")

    heatmap = _build_daily_heatmap(request.user)
    return render(
        request,
        "skill_assessment/skill_profile.html",
        {
            "skill_profile": skill_profile,
            "assessment": assessment,
            "medium_topics": skill_profile.assessment_snapshot.get("medium_topics", []),
            "coding_breakdown": skill_profile.assessment_snapshot.get(
                "coding_breakdown",
                {},
            ),
            "daily_heatmap_weeks": heatmap["weeks"],
            "daily_heatmap_summary": heatmap["summary"],
        },
    )


@admin_required
def adminpanel_skill_overview(request):
    ensure_default_assessment_content()
    query = request.GET.get("q", "").strip()
    level_filter = request.GET.get("level", "").strip()
    page_number = request.GET.get("page")

    skill_qs = StudentSkill.objects.select_related("student").order_by("-updated_at")
    if query:
        skill_qs = skill_qs.filter(
            Q(student__username__icontains=query) | Q(student__email__icontains=query)
        )
    if level_filter:
        skill_qs = skill_qs.filter(skill_level=level_filter)

    paginator = Paginator(skill_qs, 12)
    page_obj = paginator.get_page(page_number)

    level_counts = (
        StudentSkill.objects.values("skill_level")
        .annotate(total=Count("id"))
        .order_by("skill_level")
    )

    weak_topic_counts = {}
    for profile in StudentSkill.objects.only("weak_topics"):
        for topic in profile.weak_topics.keys():
            title = topic.title()
            weak_topic_counts[title] = weak_topic_counts.get(title, 0) + 1

    weak_topic_rows = [
        {"label": label, "value": value}
        for label, value in sorted(
            weak_topic_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    context = {
        "current_section": "skills",
        "page_obj": page_obj,
        "query": query,
        "level_filter": level_filter,
        "level_choices": [choice[0] for choice in StudentSkill.LEVEL_CHOICES],
        "level_labels": [item["skill_level"] for item in level_counts],
        "level_values": [item["total"] for item in level_counts],
        "weak_topic_rows": weak_topic_rows,
    }
    return render(request, "adminpanel/skills.html", context)


@admin_required
def adminpanel_skill_reset(request, student_id):
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("adminpanel_skills")

    student = get_object_or_404(User, id=student_id, role="student")
    reset_student_assessment(student)
    messages.success(request, f"Skill assessment reset for {student.username}.")
    return redirect("adminpanel_skills")
