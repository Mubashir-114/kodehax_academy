from teacher.models import Assignment, ClassRoom


ACTIVE_CLASSROOM_SESSION_KEY = "student_active_classroom_id"


def resolve_active_student_classroom(request, joined_classrooms):
    resolver_match = getattr(request, "resolver_match", None)
    kwargs = getattr(resolver_match, "kwargs", {}) or {}
    view_name = getattr(resolver_match, "view_name", "")
    classroom = None

    def find_classroom(classroom_id):
        if classroom_id is None:
            return None
        return next(
            (item for item in joined_classrooms if item.id == int(classroom_id)),
            None,
        )

    class_id = kwargs.get("class_id")
    if class_id is not None:
        classroom = find_classroom(class_id)
    elif view_name in {"course_readme_view", "course_readme_edit"}:
        classroom = find_classroom(kwargs.get("id"))
    elif "assignment_id" in kwargs:
        assignment = (
            Assignment.objects.filter(
                id=kwargs["assignment_id"],
                classroom__students=request.user,
            )
            .select_related("classroom")
            .first()
        )
        classroom = assignment.classroom if assignment else None

    if classroom:
        request.session[ACTIVE_CLASSROOM_SESSION_KEY] = classroom.id
        return classroom

    session_classroom_id = request.session.get(ACTIVE_CLASSROOM_SESSION_KEY)
    if session_classroom_id:
        classroom = find_classroom(session_classroom_id)
        if classroom:
            return classroom

    classroom = joined_classrooms[0] if joined_classrooms else None
    if classroom:
        request.session[ACTIVE_CLASSROOM_SESSION_KEY] = classroom.id
    return classroom


def student_nav_context(request):
    if not request.user.is_authenticated:
        return {}

    if getattr(request.user, "role", None) != "student":
        return {}

    joined_classrooms = getattr(request, "_student_classrooms", None)
    if joined_classrooms is None:
        joined_classrooms = list(
            ClassRoom.objects.filter(students=request.user).order_by("name", "id")
        )
    else:
        joined_classrooms = sorted(
            joined_classrooms,
            key=lambda classroom: (classroom.name, classroom.id),
        )
    active_classroom = resolve_active_student_classroom(request, joined_classrooms)
    return {
        "student_classrooms": joined_classrooms,
        "active_student_classroom": active_classroom,
    }
