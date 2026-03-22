from django import template
from django.urls import NoReverseMatch, reverse

register = template.Library()


TEACHER_LABELS = {
    "teacher_dashboard": ["Dashboard"],
    "create_class": ["Create Classroom"],
    "class_detail": ["Classroom"],
    "assignment_type_selector": ["Assignments", "Assignment Type"],
    "create_assignment": ["Assignments", "New Assignment"],
    "create_file_assignment": ["Assignments", "New File Assignment"],
    "create_quiz_assignment": ["Assignments", "New Assignment"],
    "create_code_assignment": ["Assignments", "New Coding Assignment"],
    "assignment_list": ["Assignments"],
    "assignments_page": ["Assignments"],
    "assignment_detail": ["Assignments", "Details"],
    "delete_assignment": ["Assignments", "Details"],
    "extend_assignment_deadline": ["Assignments", "Details"],
    "auto_grade_quiz": ["Assignments", "Details"],
    "grade_file_submission": ["Assignments", "Grade Submission"],
    "grade_code_submission": ["Assignments", "Grade Submission"],
    "evaluate_code_submission": ["Assignments", "Code Evaluation"],
    "performance_list": ["Performance"],
    "student_performance": ["Performance", "Student Detail"],
    "remove_student_from_classroom": ["Classroom"],
    "teacher_profile": ["Profile"],
    "teacher_edit_profile": ["Profile", "Edit"],
    "ai_tools": ["AI Tools"],
    "teacher_submit_question_template": ["Daily Challenge", "Question Template"],
}

STUDENT_LABELS = {
    "student_dashboard": ["Dashboard"],
    "student_performance_dashboard": ["Performance"],
    "join_classroom": ["Join Classroom"],
    "student_class_detail": ["Classes", "Class Detail"],
    "view_assignments": ["Assignments"],
    "submit_assignment": ["Assignments", "Submission"],
    "take_quiz_assignment": ["Assignments", "Assignment"],
    "submit_code_assignment": ["Assignments", "Code Submission"],
    "student_profile": ["Profile"],
    "edit_student_profile": ["Profile", "Edit"],
    "chat_page": ["Chatroom"],
    "ai_chat": ["Chatroom"],
    "skill_assessment_entry": ["Skill Assessment"],
    "skill_assessment_step": ["Skill Assessment", "Step"],
    "skill_assessment_complete": ["Skill Assessment", "Complete"],
    "skill_assessment_profile": ["Skill Profile"],
    "daily_challenges_today": ["Daily Challenge"],
    "daily_challenge_workspace": ["Daily Challenge", "Workspace"],
}

TEACHER_SECTION_URLS = {
    "Dashboard": lambda kwargs: _safe_reverse("teacher_dashboard"),
    "Assignments": lambda kwargs: _teacher_assignments_url(kwargs),
    "Classroom": lambda kwargs: _teacher_classroom_url(kwargs),
    "Performance": lambda kwargs: _teacher_performance_url(kwargs),
    "Profile": lambda kwargs: _safe_reverse("teacher_profile"),
    "AI Tools": lambda kwargs: _safe_reverse("ai_tools"),
    "Daily Challenge": lambda kwargs: _safe_reverse("teacher_submit_question_template"),
}

STUDENT_SECTION_URLS = {
    "Dashboard": lambda kwargs: _safe_reverse("student_dashboard"),
    "Performance": lambda kwargs: _safe_reverse("student_performance_dashboard"),
    "Classes": lambda kwargs: _safe_reverse("student_dashboard"),
    "Assignments": lambda kwargs: _safe_reverse("view_assignments"),
    "Profile": lambda kwargs: _safe_reverse("student_profile"),
    "Chatroom": lambda kwargs: _safe_reverse("chat_page"),
    "Skill Assessment": lambda kwargs: _safe_reverse("skill_assessment_entry"),
    "Skill Profile": lambda kwargs: _safe_reverse("skill_assessment_profile"),
    "Daily Challenge": lambda kwargs: _safe_reverse("daily_challenges_today"),
}


def _safe_reverse(url_name):
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return None


def _safe_reverse_with_kwargs(url_name, **kwargs):
    try:
        return reverse(url_name, kwargs=kwargs)
    except NoReverseMatch:
        return None


def _teacher_classroom_url(kwargs):
    class_id = kwargs.get("class_id") or kwargs.get("id")
    if class_id:
        return _safe_reverse_with_kwargs("class_detail", id=class_id)

    assignment_id = kwargs.get("assignment_id") or kwargs.get("id")
    if assignment_id:
        try:
            from teacher.models import Assignment

            assignment = Assignment.objects.only("classroom_id").filter(id=assignment_id).first()
            if assignment:
                return _safe_reverse_with_kwargs("class_detail", id=assignment.classroom_id)
        except Exception:
            return None

    return None


def _teacher_assignments_url(kwargs):
    class_id = kwargs.get("class_id")
    if class_id:
        return _safe_reverse_with_kwargs("assignment_list", class_id=class_id)

    assignment_id = kwargs.get("assignment_id") or kwargs.get("id")
    if assignment_id:
        try:
            from teacher.models import Assignment

            assignment = Assignment.objects.only("classroom_id").filter(id=assignment_id).first()
            if assignment:
                return _safe_reverse_with_kwargs("assignment_list", class_id=assignment.classroom_id)
        except Exception:
            return None

    submission_id = kwargs.get("submission_id")
    if submission_id:
        try:
            from teacher.models import CodeSubmission, Submission

            file_submission = Submission.objects.only("assignment__classroom_id").select_related("assignment").filter(id=submission_id).first()
            if file_submission:
                return _safe_reverse_with_kwargs("assignment_list", class_id=file_submission.assignment.classroom_id)
            code_submission = CodeSubmission.objects.only("assignment__classroom_id").select_related("assignment").filter(id=submission_id).first()
            if code_submission:
                return _safe_reverse_with_kwargs("assignment_list", class_id=code_submission.assignment.classroom_id)
        except Exception:
            return None

    return None


def _teacher_performance_url(kwargs):
    class_id = kwargs.get("class_id")
    if class_id:
        return _safe_reverse_with_kwargs("performance_list", class_id=class_id)
    return None


def _resolve_section_url(label, section_urls, kwargs):
    resolver = section_urls.get(label)
    if not resolver:
        return None
    return resolver(kwargs)


def _build_items(root_label, root_url, labels, section_urls, kwargs):
    items = [{"label": root_label, "url": root_url, "current": len(labels) == 0}]
    for index, label in enumerate(labels):
        is_current = index == len(labels) - 1
        items.append(
            {
                "label": label,
                "url": _resolve_section_url(label, section_urls, kwargs) if not is_current else None,
                "current": is_current,
            }
        )
    return items


@register.inclusion_tag("shared/breadcrumbs.html", takes_context=True)
def module_breadcrumbs(context, area):
    request = context.get("request")
    if request is None or not getattr(request, "resolver_match", None):
        return {"breadcrumb_items": []}

    route_name = request.resolver_match.url_name or ""
    kwargs = request.resolver_match.kwargs or {}

    if area == "teacher":
        labels = TEACHER_LABELS.get(route_name, [])
        root_label = "Teacher Hub"
        root_url = _safe_reverse("teacher_dashboard")
        section_urls = TEACHER_SECTION_URLS
    else:
        labels = STUDENT_LABELS.get(route_name, [])
        root_label = "Student Panel"
        root_url = _safe_reverse("student_dashboard")
        section_urls = STUDENT_SECTION_URLS

    if route_name == "skill_assessment_step":
        step = kwargs.get("step")
        labels = ["Skill Assessment", f"Step {step}"] if step else labels

    breadcrumb_items = _build_items(root_label, root_url, labels, section_urls, kwargs)
    return {"breadcrumb_items": breadcrumb_items}
