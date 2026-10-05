from django.urls import path
from . import views
from daily_challenges import views as daily_challenge_views

urlpatterns = [
    path("dashboard/",views.teacher_dashboard,name="teacher_dashboard"),
    path("class/create/",views.create_class,name="create_class"),
    path("classes/<int:id>/",views.class_detail,name="class_detail"),
    path("classes/<int:class_id>/delete/", views.delete_classroom, name="delete_classroom"),
    path("classes/<int:class_id>/notes/create/", views.create_lecture_note, name="create_lecture_note"),
    path("classes/<int:class_id>/assignments/new/", views.assignment_type_selector, name="assignment_type_selector"),
    path( "classes/<int:class_id>/assignments/create/",views.create_assignment,name="create_assignment"),
    path("classes/<int:class_id>/assignments/create/file/", views.create_file_assignment, name="create_file_assignment"),
    path("classes/<int:class_id>/assignments/create/quiz/", views.create_quiz_assignment, name="create_quiz_assignment"),
    path("classes/<int:class_id>/assignments/create/code/", views.create_code_assignment, name="create_code_assignment"),
    path("classes/<int:class_id>/assignments/",views.assignment_list,name="assignment_list"),
    path("assignments/<int:id>/",views.assignment_detail,name="assignment_detail"),
    path("assignments/<int:assignment_id>/delete/", views.delete_assignment, name="delete_assignment"),
    path("assignments/<int:assignment_id>/extend-deadline/", views.extend_assignment_deadline, name="extend_assignment_deadline"),
    path("classes/<int:class_id>/students/<int:student_id>/remove/", views.remove_student_from_classroom, name="remove_student_from_classroom"),
    path("submissions/file/<int:submission_id>/grade/", views.grade_file_submission, name="grade_file_submission"),
    path("submissions/code/<int:submission_id>/grade/", views.grade_code_submission, name="grade_code_submission"),
    path("submissions/code/<int:submission_id>/evaluate/", views.evaluate_code_submission, name="evaluate_code_submission"),
    path("assignments/<int:assignment_id>/quiz/auto-grade/", views.auto_grade_quiz, name="auto_grade_quiz"),
    path("classes/<int:class_id>/assignments/manage/",views.assignments_page,name="assignments_page"),
    path("classes/<int:class_id>/performance/",views.performance_list,name="performance_list"),
    path("classes/<int:class_id>/performance/<int:student_id>/",views.student_performance,name="student_performance"),
    path("profile/",views.teacher_profile, name="teacher_profile"),
    path("profile/edit/",views.teacher_edit_profile, name="teacher_edit_profile"),
    path("ai-tools/",views.ai_tools,name="ai_tools"),
    path("question-templates/new/", daily_challenge_views.teacher_submit_question_template, name="teacher_submit_question_template"),
]
