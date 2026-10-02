from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import BadHeaderError
from django.db.models import Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils import timezone
from datetime import timedelta
from kodehax_academy.mobile import render_for_device

from .forms import (
    ForgotPasswordForm,
    LoginForm,
    LoginOTPForm,
    ProfilePasswordChangeForm,
    ResetPasswordForm,
    StudentRegistrationForm,
    TeacherInviteRegistrationForm,
    send_password_reset_email,
    send_verification_email,
)
from .models import TeacherInvitation
from .services import (
    EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS,
    EMAIL_VERIFICATION_SESSION_KEY,
    LOGIN_OTP_MAX_ATTEMPTS,
    LOGIN_OTP_RESEND_COOLDOWN_SECONDS,
    LOGIN_OTP_SESSION_KEY,
    build_email_verification_state,
    build_login_otp_state,
    generate_login_otp,
    hash_login_otp,
    mask_email,
    now_timestamp,
    send_login_otp_email,
)
from .tokens import email_verification_token, teacher_invitation_token

User = get_user_model()


def _decode_uid(uid):
    try:
        return force_str(urlsafe_base64_decode(uid))
    except (TypeError, ValueError, OverflowError):
        return None


def _render(request, template_name, context=None, status=200):
    return render_for_device(request, template_name, context or {}, status=status)


def _login_redirect_for_role(role):
    return "teacher_login" if role == "teacher" else "student_login"


def _dashboard_redirect_for_role(role):
    return "teacher_dashboard" if role == "teacher" else "student_dashboard"


def _clear_login_otp_state(request):
    request.session.pop(LOGIN_OTP_SESSION_KEY, None)
    request.session.modified = True


def _get_login_otp_state(request):
    return request.session.get(LOGIN_OTP_SESSION_KEY)


def _store_login_otp_state(request, state):
    request.session[LOGIN_OTP_SESSION_KEY] = state
    request.session.modified = True


def _store_email_verification_state(request, user, *, cooldown=True):
    request.session[EMAIL_VERIFICATION_SESSION_KEY] = build_email_verification_state(
        user=user, cooldown=cooldown
    )
    request.session.modified = True


def _pending_email_verification_user(request):
    state = request.session.get(EMAIL_VERIFICATION_SESSION_KEY)
    if not state:
        return None, None
    user_id = state.get("user_id")
    if not user_id:
        return None, state
    user = User.objects.filter(pk=user_id, is_active=False, is_email_verified=False).first()
    if not user:
        state.pop("user_id", None)
        request.session[EMAIL_VERIFICATION_SESSION_KEY] = state
        request.session.modified = True
    return user, state


def _store_decoy_email_verification_state(request, email):
    request.session[EMAIL_VERIFICATION_SESSION_KEY] = {
        "email_hint": mask_email(email),
        "resend_available_at": now_timestamp()
        + EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS,
    }
    request.session.modified = True


def _send_login_otp(request, user, role, backend):
    otp = generate_login_otp()
    state = build_login_otp_state(user=user, role=role, backend=backend, otp=otp)
    send_login_otp_email(user, otp)
    _store_login_otp_state(request, state)


def _prepare_login_otp_context(request, form):
    state = _get_login_otp_state(request)
    if not state:
        return None
    user = User.objects.filter(pk=state.get("user_id")).only("email", "role").first()
    if not user:
        _clear_login_otp_state(request)
        return None

    current_time = now_timestamp()
    resend_available_at = state.get("resend_available_at", current_time)
    expires_at = state.get("expires_at", current_time)
    return {
        "form": form,
        "otp_email": mask_email(user.email),
        "otp_role": state.get("role", user.role),
        "resend_seconds_remaining": max(resend_available_at - current_time, 0),
        "otp_expires_seconds_remaining": max(expires_at - current_time, 0),
        "max_attempts": LOGIN_OTP_MAX_ATTEMPTS,
        "attempts_remaining": max(LOGIN_OTP_MAX_ATTEMPTS - state.get("attempts", 0), 0),
    }


def register(request):
    if request.method == "POST":
        email = request.POST.get("email", "").lower().strip()
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password1", "")
        existing_user = User.objects.filter(email__iexact=email).first() if email else None
        username_exists = bool(
            username and User.objects.filter(username__iexact=username).exists()
        )
        if existing_user or username_exists:
            if (
                existing_user
                and not existing_user.is_active
                and not existing_user.is_email_verified
                and existing_user.check_password(password)
            ):
                _store_email_verification_state(request, existing_user, cooldown=False)
            else:
                _store_decoy_email_verification_state(request, email)
            return redirect("registration_success")

    form = StudentRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        _store_email_verification_state(request, user)
        try:
            send_verification_email(request, user)
        except Exception:
            _store_email_verification_state(request, user, cooldown=False)
            messages.error(
                request,
                "Your account was saved, but the verification email could not be sent. Please try again.",
            )
        return redirect("registration_success")
    return _render(
        request,
        "accounts/register.html",
        {"form": form, "page_title": "Student registration"},
    )


def registration_success(request):
    _user, state = _pending_email_verification_user(request)
    return _render(
        request,
        "accounts/registration_success.html",
        {"can_resend_verification": bool(state)},
    )


def resend_verification(request):
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])

    user, state = _pending_email_verification_user(request)
    if not state:
        messages.info(request, "Start registration or sign in to request a verification email.")
        return redirect("student_login")

    current_time = now_timestamp()
    resend_available_at = state.get("resend_available_at", 0)
    if request.method == "POST":
        if current_time < resend_available_at:
            wait_seconds = resend_available_at - current_time
            messages.error(
                request,
                f"Please wait {wait_seconds} seconds before requesting another verification email.",
            )
        elif user:
            try:
                send_verification_email(request, user)
            except Exception:
                messages.error(request, "We couldn't send the verification email. Please try again.")
            else:
                _store_email_verification_state(request, user)
                state = request.session[EMAIL_VERIFICATION_SESSION_KEY]
                resend_available_at = state["resend_available_at"]
                messages.success(request, "A new verification link has been sent.")
        else:
            state["resend_available_at"] = (
                current_time + EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS
            )
            request.session[EMAIL_VERIFICATION_SESSION_KEY] = state
            request.session.modified = True
            resend_available_at = state["resend_available_at"]
            messages.success(
                request,
                "If the account still needs verification, a new link has been sent.",
            )

    return _render(
        request,
        "accounts/resend_verification.html",
        {
            "verification_email": state.get("email_hint", "your email address"),
            "resend_seconds_remaining": max(resend_available_at - now_timestamp(), 0),
            "resend_cooldown_seconds": EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS,
        },
    )

def verify_email(request, uid, token):
    user_id = _decode_uid(uid)
    user = User.objects.filter(pk=user_id).first() if user_id else None
    verified = False

    if user and email_verification_token.check_token(user, token):
        if not user.is_email_verified or not user.is_active:
            user.is_active = True
            user.is_email_verified = True
            user.save(update_fields=["is_active", "is_email_verified"])
        verified = True
        messages.success(request, "Email verified. You can log in now.")
    elif user and user.is_email_verified:
        verified = True
        messages.info(request, "Email already verified. You can log in now.")

    if verified:
        return redirect("student_login")

    return _render(
        request,
        "accounts/verify_email.html",
        {"verified": verified, "login_url": reverse("student_login")},
        status=400,
    )


def _login_user(request, role, template_name):
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if request.user.is_authenticated:
            current_role = "admin" if request.user.is_superuser or request.user.role == "admin" else request.user.role
            logout(request)
            messages.info(request, f"Previous {current_role} session cleared. Signing you into the requested portal.")

        username = form.cleaned_data["username"].strip()
        password = form.cleaned_data["password"]
        user = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).first()

        if not user or not user.check_password(password):
            messages.error(request, "Invalid username or password")
            return redirect(request.resolver_match.view_name)

        if role == "student" and user.role != "student":
            messages.error(request, "This account is not a student account")
            return redirect("student_login")

        if role == "teacher" and not (user.role == "teacher" or user.role == "admin" or user.is_superuser):
            messages.error(request, "This account is not a teacher or admin account")
            return redirect("teacher_login")

        if not user.is_email_verified and not user.is_superuser and user.role != "admin":
            _store_email_verification_state(request, user, cooldown=False)
            messages.info(request, "Please verify your email before logging in.")
            return redirect("resend_verification")

        if not user.is_active and not user.is_superuser and user.role != "admin":
            messages.error(request, "Your account is inactive. Please contact support.")
            return redirect(request.resolver_match.view_name)

        authenticated_user = authenticate(request, username=user.username, password=password)
        if authenticated_user is None:
            messages.error(request, "Invalid username or password")
            return redirect(request.resolver_match.view_name)

        if authenticated_user.is_superuser or authenticated_user.role == "admin":
            _clear_login_otp_state(request)
            login(request, authenticated_user)
            return redirect("adminpanel_dashboard")

        if authenticated_user.last_otp_verified_at:
            time_since_last_otp = timezone.now() - authenticated_user.last_otp_verified_at
            if time_since_last_otp < timedelta(hours=24):
                _clear_login_otp_state(request)
                login(request, authenticated_user)
                return redirect(_dashboard_redirect_for_role(authenticated_user.role))

        try:
            _send_login_otp(request, authenticated_user, role, authenticated_user.backend)
        except (OSError, BadHeaderError, Exception):
            _clear_login_otp_state(request)
            messages.error(request, "We couldn't send your verification code right now. Please try again.")
            return redirect(request.resolver_match.view_name)

        messages.success(request, f"Verification code sent to {mask_email(authenticated_user.email)}.")
        return redirect("verify_login_otp")

    return _render(request, template_name, {"form": form})


def student_login(request):
    return _login_user(request, "student", "user/login/std_login.html")


def teacher_login(request):
    return _login_user(request, "teacher", "user/login/teacher_login.html")


def verify_login_otp(request):
    state = _get_login_otp_state(request)
    if not state:
        messages.error(request, "Your verification session has expired. Please log in again.")
        return redirect("student_login")

    role = state.get("role", "student")
    form = LoginOTPForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        current_time = now_timestamp()
        if current_time > state.get("expires_at", 0):
            messages.error(request, "OTP expired. Please request a new code.")
            return redirect("verify_login_otp")

        attempts = state.get("attempts", 0)
        if attempts >= LOGIN_OTP_MAX_ATTEMPTS:
            _clear_login_otp_state(request)
            messages.error(request, "Too many invalid OTP attempts. Please log in again.")
            return redirect(_login_redirect_for_role(role))

        submitted_otp = form.cleaned_data["otp"]
        if hash_login_otp(submitted_otp) != state.get("otp_hash"):
            state["attempts"] = attempts + 1
            _store_login_otp_state(request, state)
            if state["attempts"] >= LOGIN_OTP_MAX_ATTEMPTS:
                _clear_login_otp_state(request)
                messages.error(request, "Too many invalid OTP attempts. Please log in again.")
                return redirect(_login_redirect_for_role(role))
            messages.error(request, "Invalid OTP. Please try again.")
            return redirect("verify_login_otp")

        user = get_object_or_404(User, pk=state.get("user_id"))
        backend = state.get("backend")
        if not backend:
            _clear_login_otp_state(request)
            messages.error(request, "Your verification session is invalid. Please log in again.")
            return redirect(_login_redirect_for_role(role))

        _clear_login_otp_state(request)
        user.last_otp_verified_at = timezone.now()
        user.save(update_fields=["last_otp_verified_at"])
        login(request, user, backend=backend)
        messages.success(request, "Login successful.")
        return redirect(_dashboard_redirect_for_role(user.role))

    context = _prepare_login_otp_context(request, form)
    if context is None:
        messages.error(request, "Your verification session has expired. Please log in again.")
        return redirect(_login_redirect_for_role(role))
    return _render(request, "accounts/verify_login_otp.html", context)


def resend_login_otp(request):
    state = _get_login_otp_state(request)
    if request.method != "POST" or not state:
        messages.error(request, "Your verification session has expired. Please log in again.")
        return redirect("student_login")

    role = state.get("role", "student")
    user = User.objects.filter(pk=state.get("user_id")).first()
    if not user:
        _clear_login_otp_state(request)
        messages.error(request, "Your verification session has expired. Please log in again.")
        return redirect(_login_redirect_for_role(role))

    current_time = now_timestamp()
    resend_available_at = state.get("resend_available_at", 0)
    if current_time < resend_available_at:
        wait_seconds = resend_available_at - current_time
        messages.error(request, f"Please wait {wait_seconds} seconds before requesting a new code.")
        return redirect("verify_login_otp")

    try:
        _send_login_otp(request, user, role, state.get("backend"))
    except (OSError, BadHeaderError, Exception):
        messages.error(request, "We couldn't resend your verification code right now. Please try again.")
        return redirect("verify_login_otp")

    messages.success(
        request,
        f"A new verification code was sent to {mask_email(user.email)}. Previous codes are no longer valid.",
    )
    return redirect("verify_login_otp")


def teacher_register_disabled(request):
    messages.error(request, "Teacher accounts are created through an admin invitation only.")
    return redirect("teacher_login")


def forgot_password(request):
    form = ForgotPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        user = User.objects.filter(email__iexact=email).first()
        if user:
            send_password_reset_email(request, user)
        messages.success(request, "If that email exists in our system, a password reset link has been sent.")
        return redirect("forgot_password")
    return _render(request, "accounts/forgot_password.html", {"form": form})


def reset_password(request, uid, token):
    user_id = _decode_uid(uid)
    user = User.objects.filter(pk=user_id).first() if user_id else None
    token_valid = bool(user and default_token_generator.check_token(user, token))
    form = ResetPasswordForm(user=user, data=request.POST or None) if token_valid else None

    if request.method == "POST" and token_valid and form and form.is_valid():
        user.set_password(form.cleaned_data["password1"])
        user.save(update_fields=["password"])
        messages.success(request, "Password updated successfully. You can log in now.")
        return redirect("student_login" if user.role == "student" else "teacher_login")

    return _render(
        request,
        "accounts/reset_password.html",
        {
            "form": form,
            "token_valid": token_valid,
        },
        status=200 if token_valid else 400,
    )


@login_required
def profile_change_password(request):
    user = request.user
    form = ProfilePasswordChangeForm(user=user, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        updated_user = form.save()
        update_session_auth_hash(request, updated_user)
        messages.success(request, "Password updated successfully.")
        return redirect("student_profile" if updated_user.role == "student" else "teacher_profile")

    return _render(
        request,
        "accounts/change_password.html",
        {
            "form": form,
            "base_template": "student/base.html" if user.role == "student" else "teacher/base.html",
            "cancel_url": reverse("student_profile" if user.role == "student" else "teacher_profile"),
            "page_heading": "Change Password",
            "page_subtitle": "Use your current password to authenticate before setting a new one.",
            "is_student": user.role == "student",
        },
    )


@login_required
def send_profile_password_reset(request):
    if request.method != "POST":
        return redirect("student_profile" if request.user.role == "student" else "teacher_profile")

    send_password_reset_email(request, request.user)
    messages.success(request, "A password reset link has been sent to your email address.")
    return redirect("student_profile" if request.user.role == "student" else "teacher_profile")


def teacher_invite_register(request, uid, token):
    invitation_id = _decode_uid(uid)
    invitation = TeacherInvitation.objects.filter(pk=invitation_id).first() if invitation_id else None
    token_valid = bool(invitation and not invitation.is_used and teacher_invitation_token.check_token(invitation, token))
    form = TeacherInviteRegistrationForm(invitation=invitation, data=request.POST or None) if token_valid else None

    if request.method == "POST" and token_valid and form and form.is_valid():
        form.save()
        messages.success(request, "Teacher account created. You can log in now.")
        return redirect("teacher_login")

    return _render(
        request,
        "accounts/teacher_invite_register.html",
        {
            "form": form,
            "token_valid": token_valid,
            "invitation": invitation,
        },
        status=200 if token_valid else 400,
    )
