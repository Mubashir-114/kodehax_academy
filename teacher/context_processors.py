from .models import Assignment, ClassRoom, CodeSubmission, Submission, TeacherProfile


ACTIVE_CLASSROOM_SESSION_KEY = "teacher_active_classroom_id"


def _resolve_active_classroom(request, teacher_classes):
    resolver_match = getattr(request, "resolver_match", None)
    kwargs = getattr(resolver_match, "kwargs", {}) or {}
    url_name = getattr(resolver_match, "url_name", "")
    classroom = None

    class_id = kwargs.get("class_id")
    if class_id is not None:
        classroom = teacher_classes.filter(id=class_id).first()
    elif url_name in {"class_detail", "course_readme_view", "course_readme_edit"}:
        classroom = teacher_classes.filter(id=kwargs.get("id")).first()
    elif "assignment_id" in kwargs:
        assignment = (
            Assignment.objects.filter(
                id=kwargs["assignment_id"],
                classroom__teacher=request.user,
            )
            .select_related("classroom")
            .first()
        )
        classroom = assignment.classroom if assignment else None
    elif url_name == "assignment_detail":
        assignment = (
            Assignment.objects.filter(
                id=kwargs.get("id"),
                classroom__teacher=request.user,
            )
            .select_related("classroom")
            .first()
        )
        classroom = assignment.classroom if assignment else None
    elif url_name == "grade_file_submission":
        submission = (
            Submission.objects.filter(
                id=kwargs.get("submission_id"),
                assignment__classroom__teacher=request.user,
            )
            .select_related("assignment__classroom")
            .first()
        )
        classroom = submission.assignment.classroom if submission else None
    elif url_name in {"grade_code_submission", "evaluate_code_submission"}:
        submission = (
            CodeSubmission.objects.filter(
                id=kwargs.get("submission_id"),
                assignment__classroom__teacher=request.user,
            )
            .select_related("assignment__classroom")
            .first()
        )
        classroom = submission.assignment.classroom if submission else None

    if classroom:
        request.session[ACTIVE_CLASSROOM_SESSION_KEY] = classroom.id
        return classroom

    session_classroom_id = request.session.get(ACTIVE_CLASSROOM_SESSION_KEY)
    if session_classroom_id:
        classroom = teacher_classes.filter(id=session_classroom_id).first()
        if classroom:
            return classroom

    classroom = teacher_classes.first()
    if classroom:
        request.session[ACTIVE_CLASSROOM_SESSION_KEY] = classroom.id
    return classroom


def teacher_profile_nav(request):
    if not request.user.is_authenticated:
        return {}

    if getattr(request.user, "role", None) != "teacher":
        return {}

    profile = (
        TeacherProfile.objects.filter(user=request.user)
        .only("profile_picture")
        .first()
    )
    teacher_classes = ClassRoom.objects.filter(teacher=request.user).order_by("name", "id")
    active_classroom = _resolve_active_classroom(request, teacher_classes)
    return {
        "nav_teacher_profile": profile,
        "teacher_classrooms": teacher_classes,
        "active_teacher_classroom": active_classroom,
    }
