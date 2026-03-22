from django.urls import path

from . import views
from daily_challenges import views as daily_challenge_views
from skill_assessment import views as skill_assessment_views


urlpatterns = [
    path("", views.admin_entry, name="adminpanel_home"),
    path("dashboard/", views.dashboard, name="adminpanel_dashboard"),
    path("users/", views.users, name="adminpanel_users"),
    path("users/<int:user_id>/action/", views.user_action, name="adminpanel_user_action"),
    path("users/<int:user_id>/edit/", views.user_edit, name="adminpanel_user_edit"),
    path("teachers/", views.teachers, name="adminpanel_teachers"),
    path("teachers/invite/", views.invite_teacher, name="adminpanel_invite_teacher"),
    path(
        "teachers/invitations/<int:invitation_id>/resend/",
        views.resend_teacher_invite,
        name="adminpanel_resend_teacher_invite",
    ),
    path(
        "teachers/invitations/<int:invitation_id>/delete/",
        views.delete_teacher_invite,
        name="adminpanel_delete_teacher_invite",
    ),
    path(
        "teachers/<int:teacher_id>/action/",
        views.teacher_action,
        name="adminpanel_teacher_action",
    ),
    path("students/", views.students, name="adminpanel_students"),
    path(
        "students/<int:student_id>/action/",
        views.student_action,
        name="adminpanel_student_action",
    ),
    path("assignments/", views.assignments, name="adminpanel_assignments"),
    path(
        "assignments/<int:assignment_id>/action/",
        views.assignment_action,
        name="adminpanel_assignment_action",
    ),
    path("analytics/", views.analytics, name="adminpanel_analytics"),
    path("daily-challenges/", daily_challenge_views.adminpanel_daily_challenges, name="adminpanel_daily_challenges"),
    path(
        "daily-challenges/regenerate/",
        daily_challenge_views.adminpanel_regenerate_daily_challenges,
        name="adminpanel_regenerate_daily_challenges",
    ),
    path(
        "daily-challenges/templates/import/",
        daily_challenge_views.adminpanel_import_question_templates,
        name="adminpanel_import_question_templates",
    ),
    path(
        "daily-challenges/templates/<int:template_id>/review/",
        daily_challenge_views.adminpanel_review_question_template,
        name="adminpanel_review_question_template",
    ),
    path("skills/", skill_assessment_views.adminpanel_skill_overview, name="adminpanel_skills"),
    path(
        "skills/<int:student_id>/reset/",
        skill_assessment_views.adminpanel_skill_reset,
        name="adminpanel_skill_reset",
    ),
    path(
        "settings/toggle-maintenance/",
        views.toggle_maintenance_mode,
        name="adminpanel_toggle_maintenance_mode",
    ),
    path("settings/", views.settings_view, name="adminpanel_settings"),
]
