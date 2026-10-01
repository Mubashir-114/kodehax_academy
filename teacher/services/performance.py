from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import mean

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Max, Sum
from django.utils import timezone

from daily_challenges.models import DailyChallenge, DailyChallengeSet, StudentChallengeAttempt, StudentPoints
from skill_assessment.models import CodingProblem, StudentSkill
from teacher.models import Assignment, CodeSubmission, PerformanceRecord, QuizAnswer, QuizResult, Submission

User = get_user_model()

SKILL_AREAS = (
    "Problem Solving",
    "Logic Building",
    "Python Syntax",
    "Algorithm Thinking",
    "Debugging",
)
SKILL_AREA_SLUGS = {
    "Problem Solving": "problem_solving",
    "Logic Building": "logic_building",
    "Python Syntax": "python_syntax",
    "Algorithm Thinking": "algorithm_thinking",
    "Debugging": "debugging",
}
TOPIC_SKILL_MAP = {
    "array": ("Problem Solving", "Algorithm Thinking"),
    "arrays": ("Problem Solving", "Algorithm Thinking"),
    "string": ("Logic Building", "Python Syntax"),
    "strings": ("Logic Building", "Python Syntax"),
    "loop": ("Logic Building", "Python Syntax"),
    "loops": ("Logic Building", "Python Syntax"),
    "recursion": ("Algorithm Thinking", "Problem Solving"),
    "sorting": ("Algorithm Thinking", "Logic Building"),
    "search": ("Algorithm Thinking", "Problem Solving"),
    "math": ("Problem Solving",),
    "conditionals": ("Logic Building",),
    "debugging": ("Debugging",),
    "general": ("Problem Solving",),
}
DIFFICULTY_WEIGHT = {
    DailyChallenge.DIFFICULTY_EASY: 1.0,
    DailyChallenge.DIFFICULTY_MEDIUM: 1.45,
    DailyChallenge.DIFFICULTY_HARD: 1.9,
}
PALETTE_BY_LEVEL = {
    "Beginner": "rose",
    "Intermediate": "amber",
    "Advanced": "emerald",
}


def _safe_round(value, digits=1):
    return round(float(value or 0), digits)


def _clamp(value, lower=0, upper=100):
    return max(lower, min(upper, value))


def _percent(part, whole, digits=1):
    if not whole:
        return 0
    return round((part / whole) * 100, digits)


def _score_band(score):
    if score >= 71:
        return "Advanced"
    if score >= 41:
        return "Intermediate"
    return "Beginner"


def _trend_payload(label, delta):
    direction = "up" if delta > 0.75 else "down" if delta < -0.75 else "flat"
    arrow = "▲" if direction == "up" else "▼" if direction == "down" else "•"
    tone = "emerald" if direction == "up" else "rose" if direction == "down" else "slate"
    return {
        "label": label,
        "delta": _safe_round(delta, 1),
        "display": f"{arrow} {_safe_round(abs(delta), 1)}",
        "direction": direction,
        "tone": tone,
    }


def _meter(label, value, suffix="", tone="sky", helper=""):
    return {
        "label": label,
        "value": int(round(_clamp(value))),
        "display": f"{int(round(_clamp(value)))}{suffix}",
        "tone": tone,
        "helper": helper,
    }


def _topic_skills(topic):
    normalized = (topic or "general").strip().lower()
    return TOPIC_SKILL_MAP.get(normalized, ("Problem Solving",))


def _collect_students(queryset_or_iterable):
    if hasattr(queryset_or_iterable, "values_list"):
        return list(queryset_or_iterable.distinct())
    unique = {}
    for student in queryset_or_iterable:
        unique[student.id] = student
    return list(unique.values())


def _attempts_queryset(student=None, classroom=None, since=None, until=None):
    qs = StudentChallengeAttempt.objects.select_related("student", "challenge", "challenge__problem")
    if student:
        qs = qs.filter(student=student)
    if classroom:
        qs = qs.filter(student__enrolled_classes=classroom)
    if since:
        qs = qs.filter(submitted_at__gte=since)
    if until:
        qs = qs.filter(submitted_at__lt=until)
    return qs.distinct()


def _records_queryset(student=None, classroom=None):
    qs = PerformanceRecord.objects.select_related("student", "classroom")
    if student:
        qs = qs.filter(student=student)
    if classroom:
        qs = qs.filter(classroom=classroom)
    return qs


def _student_accuracy(student, days=30):
    since = timezone.now() - timedelta(days=days)
    attempts = _attempts_queryset(student=student, since=since)
    total = attempts.count()
    solved = attempts.filter(solved=True).count()
    return _percent(solved, total, 1), total


def _student_solving_speed(student, days=30):
    since = timezone.now() - timedelta(days=days)
    solved = DailyChallenge.objects.filter(
        student=student,
        updated_at__gte=since,
        status=DailyChallenge.STATUS_SOLVED,
    )
    durations = []
    for challenge in solved:
        start = challenge.created_at or challenge.updated_at
        end = challenge.updated_at or challenge.created_at
        if start and end and end >= start:
            durations.append((end - start).total_seconds() / 60)
    if not durations:
        return 0
    return _clamp(100 - (mean(durations) * 2.2))


def _student_consistency_score(student, days=30):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    active_days = DailyChallengeSet.objects.filter(
        student=student,
        date__gte=start,
    ).values("date").distinct().count()
    return _percent(active_days, days, 0)


def _student_error_rate(student, days=30):
    since = timezone.now() - timedelta(days=days)
    attempts = _attempts_queryset(student=student, since=since)
    total = attempts.count()
    if not total:
        return 0
    compile_errors = attempts.aggregate(total=Sum("compilation_errors"))["total"] or 0
    failed_tests = attempts.aggregate(total=Sum("failed_tests"))["total"] or 0
    return _clamp(((compile_errors + failed_tests) / total) * 5)


def calculate_dynamic_skill_score(student):
    accuracy, accuracy_attempts = _student_accuracy(student)
    speed_score = _student_solving_speed(student)
    consistency_score = _student_consistency_score(student)
    error_penalty = _student_error_rate(student)

    solved = DailyChallenge.objects.filter(student=student, status=DailyChallenge.STATUS_SOLVED)
    weighted_points = 0
    weighted_max = 0
    for challenge in solved:
        weight = DIFFICULTY_WEIGHT.get(challenge.difficulty, 1.0)
        weighted_points += weight * 100
        weighted_max += 1.9 * 100
    difficulty_score = (weighted_points / weighted_max) * 100 if weighted_max else 0

    assessment = StudentSkill.objects.filter(student=student).first()
    assessment_score = float(assessment.skill_score) if assessment else 0

    final_score = (
        (accuracy * 0.30)
        + (difficulty_score * 0.20)
        + (speed_score * 0.15)
        + (consistency_score * 0.20)
        + (max(0, 100 - error_penalty) * 0.10)
        + (assessment_score * 0.05)
    )
    final_score = _clamp(round(final_score))

    if assessment and abs(float(assessment.skill_score) - final_score) >= 2:
        assessment.skill_score = final_score
        assessment.skill_level = _score_band(final_score)
        assessment.save(update_fields=["skill_score", "skill_level", "updated_at"])
    elif not assessment:
        StudentSkill.objects.create(
            student=student,
            skill_score=final_score,
            skill_level=_score_band(final_score),
        )

    return {
        "score": final_score,
        "category": _score_band(final_score),
        "accuracy_score": int(round(accuracy)),
        "speed_score": int(round(speed_score)),
        "consistency_score": int(round(consistency_score)),
        "error_penalty": int(round(error_penalty)),
        "attempt_volume": accuracy_attempts,
    }


def _build_skill_snapshot(student):
    snapshot = {area: 32 for area in SKILL_AREAS}
    attempts = _attempts_queryset(student=student)
    for attempt in attempts:
        weight = DIFFICULTY_WEIGHT.get(attempt.challenge.difficulty, 1.0) * (2 if attempt.solved else 0.8)
        for skill in _topic_skills(attempt.challenge.problem.topic):
            snapshot[skill] += 6 * weight

    total_attempts = attempts.count()
    compile_errors = attempts.aggregate(total=Sum("compilation_errors"))["total"] or 0
    failed_tests = attempts.aggregate(total=Sum("failed_tests"))["total"] or 0
    if total_attempts:
        snapshot["Debugging"] = _clamp(
            70 - ((compile_errors + failed_tests) / total_attempts) * 4 + (attempts.filter(solved=True).count() * 1.3)
        )

    assessment = StudentSkill.objects.filter(student=student).first()
    assessment_snapshot = assessment.assessment_snapshot if assessment else {}
    for area in SKILL_AREAS:
        area_key = SKILL_AREA_SLUGS[area]
        boost = assessment_snapshot.get(area_key) or assessment_snapshot.get(area.lower())
        if boost is not None:
            snapshot[area] = (snapshot[area] * 0.75) + (float(boost) * 0.25)

    return [
        {
            "label": area,
            "value": int(round(_clamp(score))),
            "tone": ("emerald" if score >= 75 else "amber" if score >= 50 else "rose"),
        }
        for area, score in snapshot.items()
    ]


def get_skill_snapshot(student):
    return {item["label"]: item["value"] for item in _build_skill_snapshot(student)}


def _average_skill_values(students):
    students = _collect_students(students)
    if not students:
        return {area: 0 for area in SKILL_AREAS}

    totals = {area: 0 for area in SKILL_AREAS}
    for student in students:
        for item in _build_skill_snapshot(student):
            totals[item["label"]] += item["value"]

    return {area: int(round(totals[area] / len(students))) for area in SKILL_AREAS}


def _skill_growth(student, label, skills):
    now = timezone.now()
    current_since = now - timedelta(days=7)
    previous_since = now - timedelta(days=14)

    current_attempts = _attempts_queryset(student=student, since=current_since)
    previous_attempts = _attempts_queryset(student=student, since=previous_since, until=current_since)

    def window_score(qs):
        relevant = [attempt for attempt in qs if any(skill in _topic_skills(attempt.challenge.problem.topic) for skill in skills)]
        if not relevant:
            return 0
        solved = len([item for item in relevant if item.solved])
        quality = mean(
            _clamp(
                55
                + (18 if item.solved else -12)
                - (item.compilation_errors * 4)
                - (item.failed_tests * 2)
                + (DIFFICULTY_WEIGHT.get(item.challenge.difficulty, 1.0) * 8)
            )
            for item in relevant
        )
        return quality + _percent(solved, len(relevant), 0) * 0.25

    return _trend_payload(label, window_score(current_attempts) - window_score(previous_attempts))


def _skill_growth_indicators(student):
    return [
        _skill_growth(student, "Logic Skill Change", ("Logic Building",)),
        _skill_growth(student, "Debugging Skill Change", ("Debugging",)),
        _skill_growth(student, "Algorithm Skill Change", ("Algorithm Thinking",)),
    ]


def _calculate_streak(student):
    dates = set(DailyChallengeSet.objects.filter(student=student, solved_count__gt=0).values_list("date", flat=True))
    if not dates:
        return {"days": 0, "label": "No active streak", "tone": "slate"}

    streak = 0
    cursor = timezone.localdate()
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)

    tone = "emerald" if streak >= 10 else "amber" if streak >= 5 else "rose"
    return {
        "days": streak,
        "label": f"{streak} Day Coding Streak" if streak else "No active streak",
        "tone": tone,
    }


def _progress_timeline(student):
    current = calculate_dynamic_skill_score(student)["score"]
    previous_score = 0
    assessment = StudentSkill.objects.filter(student=student).first()
    if assessment:
        previous_score = max(float(assessment.skill_score) - 8, 0)

    current_level = _score_band(current)
    previous_level = _score_band(previous_score)
    levels = ("Beginner", "Intermediate", "Advanced")
    return [
        {
            "label": level,
            "active": levels.index(level) <= levels.index(current_level),
            "current": level == current_level,
            "passed": levels.index(level) < levels.index(current_level),
            "just_reached": previous_level != current_level and level == current_level,
        }
        for level in levels
    ]


def _coding_behavior(student):
    attempts = _attempts_queryset(student=student)
    total = attempts.count()
    compile_errors = attempts.aggregate(total=Sum("compilation_errors"))["total"] or 0
    failed_tests = attempts.aggregate(total=Sum("failed_tests"))["total"] or 0
    solved_challenges = DailyChallenge.objects.filter(student=student, status=DailyChallenge.STATUS_SOLVED)

    avg_attempts = solved_challenges.aggregate(avg=Avg("attempts"))["avg"] or 0 if solved_challenges.exists() else 0
    solving_minutes = []
    for challenge in solved_challenges:
        if challenge.updated_at and challenge.created_at and challenge.updated_at >= challenge.created_at:
            solving_minutes.append((challenge.updated_at - challenge.created_at).total_seconds() / 60)

    avg_solving_time = mean(solving_minutes) if solving_minutes else 0
    compile_error_rate = _percent(compile_errors, total, 1)
    failed_test_rate = _percent(failed_tests, total, 1)
    consistency = calculate_dynamic_skill_score(student)["consistency_score"]

    return [
        {"label": "Average Attempts", "value": f"{_safe_round(avg_attempts, 1)}", "tone": "sky"},
        {"label": "Average Solving Time", "value": f"{int(round(avg_solving_time))} min", "tone": "violet"},
        {"label": "Compile Error Rate", "value": f"{compile_error_rate}%", "tone": "rose"},
        {"label": "Failed Test Rate", "value": f"{failed_test_rate}%", "tone": "amber"},
        {"label": "Consistency", "value": f"{consistency}%", "tone": "emerald"},
    ]


def get_coding_behavior_insights(student):
    metrics = _coding_behavior(student)
    lookup = {item["label"]: item["value"] for item in metrics}
    consistency_value = int(str(lookup["Consistency"]).rstrip("%"))
    consistency = "High" if consistency_value >= 70 else "Medium" if consistency_value >= 40 else "Low"
    return {
        "avg_attempts": lookup["Average Attempts"],
        "compile_error_rate": lookup["Compile Error Rate"],
        "consistency": consistency,
    }


def _heatmap_counts(student=None, classroom=None, days=84):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    counts = defaultdict(int)
    set_qs = DailyChallengeSet.objects.filter(date__gte=start)
    if student:
        set_qs = set_qs.filter(student=student)
    if classroom:
        set_qs = set_qs.filter(student__enrolled_classes=classroom)

    for row in set_qs.values("date").annotate(count=Sum("solved_count")):
        counts[row["date"]] += row["count"] or 0

    record_qs = PerformanceRecord.objects.filter(submitted_at__date__gte=start)
    if student:
        record_qs = record_qs.filter(student=student)
    if classroom:
        record_qs = record_qs.filter(classroom=classroom)
    for row in record_qs.values("submitted_at__date").annotate(count=Count("id")):
        if row["submitted_at__date"]:
            counts[row["submitted_at__date"]] += row["count"]
    return counts, start, today


def get_student_activity_heatmap(student=None, classroom=None):
    counts, start, today = _heatmap_counts(student=student, classroom=classroom, days=365)
    heatmap = []
    current = start
    while current <= today:
        heatmap.append({"date": current.isoformat(), "count": counts.get(current, 0)})
        current += timedelta(days=1)
    return heatmap


def _heatmap_weeks(student=None, classroom=None, scope_students=None, days=84):
    counts, start, today = _heatmap_counts(student=student, classroom=classroom, days=days)
    if scope_students is not None:
        counts = defaultdict(int)
        for student_item in _collect_students(scope_students):
            student_counts, _, _ = _heatmap_counts(student=student_item, days=days)
            for day, value in student_counts.items():
                counts[day] += value

    offset_start = start - timedelta(days=(start.weekday() + 1) % 7)
    weeks = []
    cursor = offset_start
    while cursor <= today:
        week = []
        for _ in range(7):
            count = counts.get(cursor, 0)
            level = 0
            if count >= 6:
                level = 4
            elif count >= 4:
                level = 3
            elif count >= 2:
                level = 2
            elif count == 1:
                level = 1
            week.append({
                "date": cursor,
                "count": count,
                "level": level,
                "in_range": start <= cursor <= today,
            })
            cursor += timedelta(days=1)
        weeks.append(week)
    return weeks


def _completion_for_queryset(challenges):
    total = challenges.count()
    solved = challenges.filter(status=DailyChallenge.STATUS_SOLVED).count()
    return solved, total, _percent(solved, total, 1)


def _daily_challenge_cards(scope_students=None, classroom=None, target_date=None):
    target_date = target_date or timezone.localdate()
    challenges = DailyChallenge.objects.filter(date=target_date)
    if scope_students is not None:
        student_ids = [student.id for student in _collect_students(scope_students)]
        challenges = challenges.filter(student_id__in=student_ids)
    if classroom:
        challenges = challenges.filter(student__enrolled_classes=classroom)

    cards = []
    for difficulty, label in (
        (DailyChallenge.DIFFICULTY_EASY, "Easy"),
        (DailyChallenge.DIFFICULTY_MEDIUM, "Medium"),
        (DailyChallenge.DIFFICULTY_HARD, "Hard"),
    ):
        subset = challenges.filter(difficulty=difficulty)
        solved, total, rate = _completion_for_queryset(subset)
        cards.append({
            "label": label,
            "rate": rate,
            "solved": solved,
            "total": total,
            "tone": "emerald" if rate >= 70 else "amber" if rate >= 40 else "rose",
        })
    return cards


def _difficulty_balance(scope_students=None, classroom=None, target_date=None):
    target_date = target_date or timezone.localdate()
    qs = DailyChallenge.objects.filter(date=target_date)
    if scope_students is not None:
        student_ids = [student.id for student in _collect_students(scope_students)]
        qs = qs.filter(student_id__in=student_ids)
    if classroom:
        qs = qs.filter(student__enrolled_classes=classroom)

    counts = {key: qs.filter(difficulty=key).count() for key in ("easy", "medium", "hard")}
    total = sum(counts.values())
    ideal = total / 3 if total else 0
    spread = max(counts.values()) - min(counts.values()) if total else 0
    if not total:
        label = "No daily challenges"
        tone = "slate"
    elif spread <= max(2, ideal * 0.15):
        label = "Well balanced"
        tone = "emerald"
    elif spread <= max(4, ideal * 0.35):
        label = "Slightly uneven"
        tone = "amber"
    else:
        label = "Needs rebalance"
        tone = "rose"
    return {
        "counts": counts,
        "label": label,
        "tone": tone,
        "segments": [
            {"label": "Easy", "value": counts["easy"], "percent": _percent(counts["easy"], total, 0)},
            {"label": "Medium", "value": counts["medium"], "percent": _percent(counts["medium"], total, 0)},
            {"label": "Hard", "value": counts["hard"], "percent": _percent(counts["hard"], total, 0)},
        ],
    }


def _achievement_tag(total_points, accuracy, speed_score):
    if accuracy >= 85:
        return "Highest Accuracy"
    if speed_score >= 80:
        return "Fastest Solver"
    if total_points >= 300:
        return "Consistency Machine"
    return "Rising Solver"


def _leaderboard(scope_students=None, limit=5):
    points_qs = StudentPoints.objects.select_related("student").order_by("-total_points", "student__username")
    if scope_students is not None:
        student_ids = [student.id for student in _collect_students(scope_students)]
        points_qs = points_qs.filter(student_id__in=student_ids)

    entries = []
    for rank, points in enumerate(points_qs[:limit], start=1):
        profile = calculate_dynamic_skill_score(points.student)
        accuracy, _ = _student_accuracy(points.student)
        entries.append({
            "rank": rank,
            "student": points.student,
            "points": points.total_points,
            "daily_points": points.daily_points,
            "points_remaining": points.points_remaining,
            "skill_score": profile["score"],
            "achievement_tag": _achievement_tag(points.total_points, accuracy, profile["speed_score"]),
            "accuracy": int(round(accuracy)),
        })
    return entries


def get_struggling_students(students_queryset, limit=5):
    now = timezone.now()
    threshold = now - timedelta(days=7)
    attention_rows = []

    for student in _collect_students(students_queryset):
        attempts = _attempts_queryset(student=student, since=threshold)
        total_attempts = attempts.count()
        failed_attempts = attempts.filter(solved=False).count()
        compile_errors = attempts.aggregate(total=Sum("compilation_errors"))["total"] or 0
        record_last = _records_queryset(student=student).aggregate(last=Max("recorded_at"))["last"]
        challenge_last = DailyChallengeSet.objects.filter(student=student).aggregate(last=Max("updated_at"))["last"]
        last_activity = max(filter(None, [record_last, challenge_last]), default=None)
        accuracy = _percent(attempts.filter(solved=True).count(), total_attempts, 1)
        skill_score = calculate_dynamic_skill_score(student)["score"]

        reasons = []
        if failed_attempts >= 4:
            reasons.append("multiple failed attempts")
        if total_attempts >= 3 and accuracy < 40:
            reasons.append("low accuracy")
        if compile_errors >= 6:
            reasons.append("repeated compile errors")
        if not last_activity or last_activity < now - timedelta(days=5):
            reasons.append("inactivity")

        if reasons:
            attention_rows.append({
                "student": student,
                "reasons": reasons,
                "reason": ", ".join(reasons[:2]),
                "accuracy": accuracy,
                "failed_attempts": failed_attempts,
                "compile_errors": compile_errors,
                "skill_score": skill_score,
                "last_active": last_activity,
                "value": f"{failed_attempts} fails / {accuracy}%",
            })

    attention_rows.sort(key=lambda row: (-len(row["reasons"]), row["accuracy"], row["skill_score"]))
    return attention_rows[:limit]


def _question_difficulty_analytics():
    rows = []
    for problem in CodingProblem.objects.filter(is_active=True):
        challenges = DailyChallenge.objects.filter(problem=problem)
        total = challenges.count()
        if not total:
            continue
        solved = challenges.filter(status=DailyChallenge.STATUS_SOLVED).count()
        avg_attempts = challenges.aggregate(avg=Avg("attempts"))["avg"] or 0
        success_rate = _percent(solved, total, 1)
        if success_rate >= 80 and avg_attempts <= 1.8:
            indicator = "Too easy"
            tone = "amber"
        elif success_rate <= 30 and avg_attempts >= 3:
            indicator = "Too difficult"
            tone = "rose"
        else:
            indicator = "Balanced"
            tone = "emerald"
        rows.append({
            "problem": problem,
            "success_rate": success_rate,
            "average_attempts": _safe_round(avg_attempts, 1),
            "difficulty_validation": indicator,
            "tone": tone,
            "sample_size": total,
        })
    rows.sort(key=lambda row: (row["success_rate"], -row["average_attempts"]))
    return rows[:8]


def _teacher_insights(students, scope_label="students"):
    students = _collect_students(students)
    total_students = len(students)
    if not total_students:
        return []

    hard_challenges = DailyChallenge.objects.filter(student__in=students, difficulty=DailyChallenge.DIFFICULTY_HARD)
    hard_total = hard_challenges.count()
    hard_failed = hard_challenges.exclude(status=DailyChallenge.STATUS_SOLVED).values("student_id").distinct().count()

    inactive = 0
    logic_deltas = []
    debugging_deltas = []
    for student in students:
        if _calculate_streak(student)["days"] == 0:
            inactive += 1
        logic_deltas.append(_skill_growth(student, "Logic", ("Logic Building",))["delta"])
        debugging_deltas.append(_skill_growth(student, "Debugging", ("Debugging",))["delta"])

    return [
        {
            "title": "Hard problem friction",
            "value": f"{_percent(hard_failed, total_students, 0)}%",
            "description": f"of {scope_label} struggled with hard daily challenges",
            "tone": "rose" if hard_total and _percent(hard_failed, total_students, 0) >= 45 else "amber",
        },
        {
            "title": "Logic trend",
            "value": f"{'+' if mean(logic_deltas) >= 0 else ''}{_safe_round(mean(logic_deltas), 1)}",
            "description": "weekly logic-building shift across the cohort",
            "tone": "emerald" if mean(logic_deltas) > 0 else "rose" if mean(logic_deltas) < 0 else "slate",
        },
        {
            "title": "Debugging trend",
            "value": f"{'+' if mean(debugging_deltas) >= 0 else ''}{_safe_round(mean(debugging_deltas), 1)}",
            "description": "weekly debugging movement across the cohort",
            "tone": "emerald" if mean(debugging_deltas) > 0 else "rose" if mean(debugging_deltas) < 0 else "slate",
        },
        {
            "title": "Inactive students",
            "value": str(inactive),
            "description": "students need a teacher follow-up this week",
            "tone": "amber" if inactive else "emerald",
        },
    ]


def _class_skill_distribution(students):
    distribution = {"Beginner": 0, "Intermediate": 0, "Advanced": 0}
    for student in _collect_students(students):
        distribution[calculate_dynamic_skill_score(student)["category"]] += 1
    return [{"label": label, "count": count, "tone": PALETTE_BY_LEVEL[label]} for label, count in distribution.items()]


def _student_card(student, total_assignments=None):
    profile = calculate_dynamic_skill_score(student)
    records = _records_queryset(student=student)
    completed = records.filter(submitted_at__isnull=False).values("original_assignment_id").distinct().count()
    avg_score = records.filter(score__isnull=False).aggregate(avg=Avg("score"))["avg"] or 0
    accuracy, _ = _student_accuracy(student)
    snapshot = _build_skill_snapshot(student)
    strongest = max(snapshot, key=lambda item: item["value"])
    weakest = min(snapshot, key=lambda item: item["value"])
    completion = _percent(completed, total_assignments, 0) if total_assignments is not None else accuracy
    return {
        "student": student,
        "skill_score": profile["score"],
        "category": profile["category"],
        "average_score": _safe_round(avg_score, 1),
        "completion_rate": completion,
        "accuracy": int(round(accuracy)),
        "streak": _calculate_streak(student)["days"],
        "strongest_skill": strongest["label"],
        "weakest_skill": weakest["label"],
    }


def _cohort_behavior_metrics(students):
    students = _collect_students(students)
    if not students:
        return []
    per_student = [_coding_behavior(student) for student in students]
    labels = [item["label"] for item in per_student[0]]
    metrics = []
    for index, label in enumerate(labels):
        raw_values = [student_metrics[index]["value"] for student_metrics in per_student]
        numbers = []
        for value in raw_values:
            cleaned = str(value).replace("%", "").replace(" min", "")
            try:
                numbers.append(float(cleaned))
            except ValueError:
                continue
        avg = mean(numbers) if numbers else 0
        suffix = "%" if "%" in str(raw_values[0]) else " min" if "min" in str(raw_values[0]) else ""
        display = f"{_safe_round(avg, 1)}{suffix}".replace(".0%", "%").replace(".0 min", " min")
        metrics.append({"label": label, "value": display, "tone": per_student[0][index]["tone"]})
    return metrics[:4]


def _recent_activity_rows(scope_students=None, classroom=None, limit=6):
    records = _records_queryset(classroom=classroom).filter(submitted_at__isnull=False)
    if scope_students is not None:
        student_ids = [student.id for student in _collect_students(scope_students)]
        records = records.filter(student_id__in=student_ids)
    return list(records.order_by("-submitted_at")[:limit])


def _summarize_heatmap_weeks(weeks):
    cells = [cell for week in weeks for cell in week if cell["in_range"]]
    if not cells:
        return {
            "active_days": 0,
            "total_activity": 0,
            "best_day": None,
            "consistency": 0,
        }

    active_days = len([cell for cell in cells if cell["count"] > 0])
    total_activity = sum(cell["count"] for cell in cells)
    best_day = max(cells, key=lambda cell: cell["count"])
    return {
        "active_days": active_days,
        "total_activity": total_activity,
        "best_day": best_day,
        "consistency": _percent(active_days, len(cells), 0),
    }


def get_teacher_dashboard_analytics(teacher):
    classrooms = teacher.teacher_classes.prefetch_related("students").all()
    students = _collect_students(User.objects.filter(enrolled_classes__teacher=teacher, role="student"))
    overview = {
        "classes": classrooms.count(),
        "students": len(students),
        "assignments": Assignment.objects.filter(classroom__teacher=teacher).count(),
        "average_skill": int(round(mean([calculate_dynamic_skill_score(student)["score"] for student in students]) if students else 0)),
    }

    heatmap_weeks = _heatmap_weeks(scope_students=students)
    return {
        "overview": overview,
        "meters": [
            _meter("Skill Summary", overview["average_skill"], tone="sky", helper="average class skill score"),
            _meter("Coding Streak", int(round(mean([_calculate_streak(student)["days"] for student in students]) if students else 0)), suffix="d", tone="amber", helper="average active streak"),
            _meter("Accuracy", int(round(mean([_student_accuracy(student)[0] for student in students]) if students else 0)), suffix="%", tone="emerald", helper="class challenge accuracy"),
        ],
        "daily_challenge_cards": _daily_challenge_cards(scope_students=students),
        "heatmap_weeks": heatmap_weeks,
        "heatmap_summary": _summarize_heatmap_weeks(heatmap_weeks),
        "skill_distribution": _class_skill_distribution(students),
        "needs_attention": get_struggling_students(students, limit=5),
        "teacher_insights": _teacher_insights(students, scope_label="students"),
        "leaderboard": _leaderboard(scope_students=students, limit=5),
        "behavior_metrics": _cohort_behavior_metrics(students),
        "challenge_balance": _difficulty_balance(scope_students=students),
    }


def get_classroom_performance_analytics(classroom):
    students = _collect_students(classroom.students.all())
    total_assignments = classroom.assignments.count()
    student_cards = [_student_card(student, total_assignments=total_assignments) for student in students]
    class_average = mean([row["average_score"] for row in student_cards]) if student_cards else 0
    average_accuracy = mean([row["accuracy"] for row in student_cards]) if student_cards else 0

    average_skills = _average_skill_values(students)
    skill_snapshot = [
        {
            "label": label,
            "value": value,
            "tone": "emerald" if value >= 75 else "amber" if value >= 50 else "rose",
        }
        for label, value in average_skills.items()
    ]

    heatmap_weeks = _heatmap_weeks(classroom=classroom)
    return {
        "summary": {
            "total_students": len(students),
            "total_assignments": total_assignments,
            "class_average_score": _safe_round(class_average, 1),
            "average_accuracy": int(round(average_accuracy)),
            "average_skill_score": int(round(mean([calculate_dynamic_skill_score(student)["score"] for student in students]) if students else 0)),
        },
        "meters": [
            _meter("Skill Summary", mean([calculate_dynamic_skill_score(student)["score"] for student in students]) if students else 0, tone="sky", helper="average dynamic skill score"),
            _meter("Class Streak", mean([_calculate_streak(student)["days"] for student in students]) if students else 0, suffix="d", tone="amber", helper="average student streak"),
            _meter("Accuracy", average_accuracy, suffix="%", tone="emerald", helper="challenge solve accuracy"),
        ],
        "skill_snapshot": skill_snapshot,
        "daily_challenge_cards": _daily_challenge_cards(classroom=classroom),
        "growth_indicators": [
            _trend_payload("Logic Skill Change", mean([_skill_growth(student, "Logic", ("Logic Building",))["delta"] for student in students]) if students else 0),
            _trend_payload("Debugging Skill Change", mean([_skill_growth(student, "Debugging", ("Debugging",))["delta"] for student in students]) if students else 0),
            _trend_payload("Algorithm Skill Change", mean([_skill_growth(student, "Algorithm", ("Algorithm Thinking",))["delta"] for student in students]) if students else 0),
        ],
        "leaderboard": _leaderboard(scope_students=students, limit=6),
        "needs_attention": get_struggling_students(students, limit=5),
        "behavior_metrics": _cohort_behavior_metrics(students),
        "heatmap_weeks": heatmap_weeks,
        "heatmap_summary": _summarize_heatmap_weeks(heatmap_weeks),
        "student_rows": sorted(student_cards, key=lambda row: (-row["skill_score"], -row["accuracy"], row["student"].username.lower())),
        "skill_distribution": _class_skill_distribution(students),
        "teacher_insights": _teacher_insights(students, scope_label="students"),
        "challenge_balance": _difficulty_balance(classroom=classroom),
        "recent_activity": _recent_activity_rows(classroom=classroom),
    }


def get_student_detail_analytics(classroom, student):
    records = _records_queryset(student=student, classroom=classroom).order_by("-submitted_at", "-recorded_at")
    profile = calculate_dynamic_skill_score(student)
    average_score = records.filter(score__isnull=False).aggregate(avg=Avg("score"))["avg"] or 0
    heatmap_weeks = _heatmap_weeks(student=student)
    return {
        "student": student,
        "average_score": _safe_round(average_score, 1),
        "skill_score": profile["score"],
        "category": profile["category"],
        "meters": [
            _meter("Accuracy Score", profile["accuracy_score"], suffix="%", tone="emerald", helper="challenge success quality"),
            _meter("Speed Score", profile["speed_score"], suffix="%", tone="sky", helper="solve speed across completed challenges"),
            _meter("Consistency Score", profile["consistency_score"], suffix="%", tone="amber", helper="active practice days"),
        ],
        "skill_snapshot": _build_skill_snapshot(student),
        "growth_indicators": _skill_growth_indicators(student),
        "progress_timeline": _progress_timeline(student),
        "streak": _calculate_streak(student),
        "behavior_metrics": _coding_behavior(student),
        "heatmap_weeks": heatmap_weeks,
        "heatmap_summary": _summarize_heatmap_weeks(heatmap_weeks),
        "records": records,
    }


def get_admin_dashboard_analytics():
    students = _collect_students(User.objects.filter(role="student", is_active=True))
    teachers = User.objects.filter(role="teacher", is_active=True)
    today = timezone.localdate()

    overview = {
        "students": len(students),
        "teachers": teachers.count(),
        "assignments": Assignment.objects.count(),
        "active_today": DailyChallengeSet.objects.filter(date=today).values("student_id").distinct().count(),
        "average_skill": int(round(mean([calculate_dynamic_skill_score(student)["score"] for student in students]) if students else 0)),
    }

    heatmap_weeks = _heatmap_weeks(scope_students=students)
    return {
        "overview": overview,
        "meters": [
            _meter("Skill Summary", overview["average_skill"], tone="sky", helper="platform-wide dynamic skill score"),
            _meter("Coding Streak", int(round(mean([_calculate_streak(student)["days"] for student in students]) if students else 0)), suffix="d", tone="amber", helper="average active streak"),
            _meter("Accuracy", int(round(mean([_student_accuracy(student)[0] for student in students]) if students else 0)), suffix="%", tone="emerald", helper="platform challenge accuracy"),
        ],
        "daily_challenge_cards": _daily_challenge_cards(scope_students=students),
        "heatmap_weeks": heatmap_weeks,
        "heatmap_summary": _summarize_heatmap_weeks(heatmap_weeks),
        "needs_attention": get_struggling_students(students, limit=6),
        "behavior_metrics": _cohort_behavior_metrics(students),
        "teacher_insights": _teacher_insights(students, scope_label="students"),
        "leaderboard": _leaderboard(scope_students=students, limit=6),
        "challenge_balance": _difficulty_balance(scope_students=students),
        "question_analytics": _question_difficulty_analytics(),
        "skill_distribution": _class_skill_distribution(students),
        "recent_activity": _recent_activity_rows(scope_students=students),
        "top_teachers": list(
            teachers.annotate(
                class_count=Count("teacher_classes", distinct=True),
                assignment_count=Count("teacher_classes__assignments", distinct=True),
            ).order_by("-assignment_count", "-class_count")[:6]
        ),
    }


def get_admin_analytics_page():
    analytics = get_admin_dashboard_analytics()
    students = _collect_students(User.objects.filter(role="student", is_active=True))
    analytics["student_spotlight"] = sorted(
        [_student_card(student) for student in students],
        key=lambda row: (-row["skill_score"], -row["accuracy"], row["student"].username.lower()),
    )[:8]
    return analytics


def _upsert_performance_record(
    *,
    student,
    assignment: Assignment,
    score,
    submitted_at,
    feedback: str,
    evaluation_type: str,
    assignment_ref=None,
    is_deleted_assignment: bool = False,
) -> PerformanceRecord:
    due_date = assignment.due_date
    was_on_time = True
    if submitted_at and due_date:
        was_on_time = submitted_at <= due_date

    record, _ = PerformanceRecord.objects.update_or_create(
        student=student,
        original_assignment_id=assignment.id,
        defaults={
            "classroom": assignment.classroom,
            "assignment": assignment_ref if assignment_ref else assignment,
            "assignment_title": assignment.title,
            "assignment_type": assignment.assignment_type,
            "score": score,
            "max_score": assignment.max_score,
            "submitted_at": submitted_at,
            "due_date_snapshot": due_date,
            "was_on_time": was_on_time,
            "evaluation_type": evaluation_type,
            "feedback": (feedback or "").strip(),
            "is_deleted_assignment": is_deleted_assignment,
        },
    )
    return record


def sync_file_submission_record(submission: Submission, evaluation_type: str) -> PerformanceRecord:
    return _upsert_performance_record(
        student=submission.student,
        assignment=submission.assignment,
        score=submission.score,
        submitted_at=submission.submitted_at,
        feedback=submission.ai_feedback,
        evaluation_type=evaluation_type,
        assignment_ref=submission.assignment,
    )


def sync_code_submission_record(code_submission: CodeSubmission, evaluation_type: str) -> PerformanceRecord:
    return _upsert_performance_record(
        student=code_submission.student,
        assignment=code_submission.assignment,
        score=code_submission.score,
        submitted_at=code_submission.submitted_at,
        feedback=code_submission.ai_feedback,
        evaluation_type=evaluation_type,
        assignment_ref=code_submission.assignment,
    )


def sync_quiz_result_record(result: QuizResult, evaluation_type: str = PerformanceRecord.EVALUATION_TYPE_AUTO) -> PerformanceRecord:
    return _upsert_performance_record(
        student=result.student,
        assignment=result.assignment,
        score=result.score,
        submitted_at=result.evaluated_at,
        feedback=result.feedback,
        evaluation_type=evaluation_type,
        assignment_ref=result.assignment,
    )


def snapshot_assignment_performance(assignment: Assignment) -> None:
    if assignment.assignment_type == Assignment.ASSIGNMENT_TYPE_FILE:
        for submission in assignment.submissions.select_related("student").all():
            _upsert_performance_record(
                student=submission.student,
                assignment=assignment,
                score=submission.score,
                submitted_at=submission.submitted_at,
                feedback=submission.ai_feedback,
                evaluation_type=PerformanceRecord.EVALUATION_TYPE_AI,
                assignment_ref=None,
                is_deleted_assignment=True,
            )
        return

    if assignment.assignment_type == Assignment.ASSIGNMENT_TYPE_CODE:
        for submission in assignment.code_submissions.select_related("student").all():
            _upsert_performance_record(
                student=submission.student,
                assignment=assignment,
                score=submission.score,
                submitted_at=submission.submitted_at,
                feedback=submission.ai_feedback,
                evaluation_type=PerformanceRecord.EVALUATION_TYPE_AI,
                assignment_ref=None,
                is_deleted_assignment=True,
            )
        return

    quiz_results = assignment.quiz_results.select_related("student").all()
    if quiz_results.exists():
        for result in quiz_results:
            _upsert_performance_record(
                student=result.student,
                assignment=assignment,
                score=result.score,
                submitted_at=result.evaluated_at,
                feedback=result.feedback,
                evaluation_type=PerformanceRecord.EVALUATION_TYPE_AUTO,
                assignment_ref=None,
                is_deleted_assignment=True,
            )
        return

    student_ids = QuizAnswer.objects.filter(question__assignment=assignment).values_list("student_id", flat=True).distinct()
    for student in assignment.classroom.students.filter(id__in=student_ids):
        _upsert_performance_record(
            student=student,
            assignment=assignment,
            score=None,
            submitted_at=None,
            feedback="Quiz attempted but no evaluated score found before deletion.",
            evaluation_type=PerformanceRecord.EVALUATION_TYPE_AUTO,
            assignment_ref=None,
            is_deleted_assignment=True,
        )


def get_student_performance_summary(student):
    records = PerformanceRecord.objects.filter(student=student).select_related("classroom").order_by("submitted_at", "recorded_at")
    active_total_assignments = Assignment.objects.filter(classroom__students=student).count()
    completed_records = records.filter(submitted_at__isnull=False)

    avg_score = completed_records.aggregate(value=Avg("score"))["value"] or 0
    highest_score = completed_records.order_by("-score").values_list("score", flat=True).first()
    lowest_score = completed_records.order_by("score").values_list("score", flat=True).first()

    completed_count = completed_records.values("original_assignment_id").distinct().count()
    on_time_count = completed_records.filter(was_on_time=True).values("original_assignment_id").distinct().count()

    completion_percentage = round((completed_count / active_total_assignments) * 100, 2) if active_total_assignments else 0
    completion_percentage = min(completion_percentage, 100.0)
    on_time_rate = round((on_time_count / completed_count) * 100, 2) if completed_count else 0

    score_labels = []
    score_values = []
    bar_labels = []
    bar_values = []
    for record in records:
        if record.score is None:
            continue
        when = record.submitted_at or record.recorded_at
        label = f"{record.assignment_title} ({when.strftime('%d %b')})"
        score_labels.append(label)
        score_values.append(round(float(record.score), 2))
        bar_labels.append(record.assignment_title)
        bar_values.append(round(float(record.score), 2))

    daily_submission_counter = defaultdict(int)
    for record in completed_records:
        when = record.submitted_at or record.recorded_at
        daily_submission_counter[when.date()] += 1

    cumulative = 0
    trend_labels = []
    trend_values = []
    for day in sorted(daily_submission_counter.keys()):
        cumulative += daily_submission_counter[day]
        trend_labels.append(day.strftime("%d %b"))
        trend_values.append(cumulative)

    return {
        "summary": {
            "average_score": round(avg_score, 2),
            "highest_score": round(float(highest_score), 2) if highest_score is not None else 0,
            "lowest_score": round(float(lowest_score), 2) if lowest_score is not None else 0,
            "assignments_completed": completed_count,
            "total_assignments": active_total_assignments,
            "completion_percentage": completion_percentage,
            "submission_rate": completion_percentage,
            "on_time_submission_rate": on_time_rate,
        },
        "records": records,
        "charts": {
            "score_progression_labels": score_labels,
            "score_progression_values": score_values,
            "assignment_score_labels": bar_labels,
            "assignment_score_values": bar_values,
            "submission_trend_labels": trend_labels,
            "submission_trend_values": trend_values,
        },
    }
