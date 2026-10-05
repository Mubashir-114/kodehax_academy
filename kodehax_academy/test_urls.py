from django.http import HttpResponse
from django.urls import include, path


def _stub_view(request):
    return HttpResponse("ok")


urlpatterns = [
    path("", include("accounts.urls")),
    path("logout/", _stub_view, name="logout"),
    path("admin-panel/dashboard/", _stub_view, name="adminpanel_dashboard"),
    path("student/", include("student.urls")),
    path("student/skill-assessment/", include("skill_assessment.urls")),
    path("student/skill-profile/", _stub_view, name="skill_assessment_profile"),
    path("student/daily-challenges/", include("daily_challenges.urls")),
    path("student/assignments/", _stub_view, name="view_assignments"),
    path("student/performance/", _stub_view, name="student_performance_dashboard"),
    path("student/chat/", _stub_view, name="chat_page"),
    path("student/profile/", _stub_view, name="student_profile"),
    path("teacher/dashboard/", _stub_view, name="teacher_dashboard"),
    path("teacher/classes/<int:id>/", _stub_view, name="class_detail"),
    path("teacher/classes/<int:class_id>/assignments/", _stub_view, name="assignment_list"),
    path("teacher/classes/<int:class_id>/performance/", _stub_view, name="performance_list"),
    path("teacher/profile/", _stub_view, name="teacher_profile"),
    path("teacher/ai-tools/", _stub_view, name="ai_tools"),
    path("teacher/question-templates/new/", _stub_view, name="teacher_submit_question_template"),
    path("accounts/profile/change-password/", _stub_view, name="profile_change_password"),
    path("accounts/profile/send-reset-link/", _stub_view, name="profile_send_reset_link"),
]
