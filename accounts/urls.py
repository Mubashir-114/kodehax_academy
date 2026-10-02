from django.urls import path

from . import views


urlpatterns = [
    path("register/", views.register, name="register"),
    path("student/register/", views.register, name="student_register"),
    path("student/registration-success/", views.registration_success, name="registration_success"),
    path("verify-email/resend/", views.resend_verification, name="resend_verification"),
    path("teacher/register/", views.teacher_register_disabled, name="teacher_register"),
    path("student/login/", views.student_login, name="student_login"),
    path("teacher/login/", views.teacher_login, name="teacher_login"),
    path("verify-otp/", views.verify_login_otp, name="verify_login_otp"),
    path("verify-otp/resend/", views.resend_login_otp, name="resend_login_otp"),
    path("verify-email/<uid>/<token>/", views.verify_email, name="verify_email"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("reset-password/<uid>/<token>/", views.reset_password, name="reset_password"),
    path("profile/change-password/", views.profile_change_password, name="profile_change_password"),
    path("profile/send-reset-link/", views.send_profile_password_reset, name="profile_send_reset_link"),
    path("teacher-invite/<uid>/<token>/", views.teacher_invite_register, name="teacher_invite_register"),
]
