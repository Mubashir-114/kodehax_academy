import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import salted_hmac


LOGIN_OTP_SESSION_KEY = "login_otp_state"
EMAIL_VERIFICATION_SESSION_KEY = "email_verification_state"
LOGIN_OTP_LENGTH = 6
LOGIN_OTP_TTL_SECONDS = getattr(settings, "LOGIN_OTP_TTL_SECONDS", 300)
LOGIN_OTP_RESEND_COOLDOWN_SECONDS = getattr(settings, "LOGIN_OTP_RESEND_COOLDOWN_SECONDS", 30)
LOGIN_OTP_MAX_ATTEMPTS = getattr(settings, "LOGIN_OTP_MAX_ATTEMPTS", 5)
EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS = getattr(
    settings, "EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS", 30
)


def now_timestamp():
    return int(timezone.now().timestamp())


def generate_login_otp():
    upper_bound = 10 ** LOGIN_OTP_LENGTH
    return f"{secrets.randbelow(upper_bound):0{LOGIN_OTP_LENGTH}d}"


def hash_login_otp(otp):
    return salted_hmac("accounts.login_otp", otp).hexdigest()


def build_login_otp_state(*, user, role, backend, otp):
    current_time = now_timestamp()
    return {
        "user_id": user.pk,
        "role": role,
        "backend": backend,
        "otp_hash": hash_login_otp(otp),
        "expires_at": current_time + LOGIN_OTP_TTL_SECONDS,
        "resend_available_at": current_time + LOGIN_OTP_RESEND_COOLDOWN_SECONDS,
        "attempts": 0,
    }


def build_email_verification_state(*, user, cooldown=True):
    current_time = now_timestamp()
    return {
        "user_id": user.pk,
        "email_hint": mask_email(user.email),
        "resend_available_at": current_time
        + (EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS if cooldown else 0),
    }


def mask_email(email):
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = f"{local[:1]}*"
    else:
        masked_local = f"{local[:2]}{'*' * max(len(local) - 2, 1)}"
    return f"{masked_local}@{domain}"


def send_login_otp_email(user, otp):
    message = render_to_string(
        "accounts/email/login_otp.txt",
        {
            "user": user,
            "otp": otp,
            "expires_minutes": LOGIN_OTP_TTL_SECONDS // 60,
            "site_name": "Kodehax Academy",
        },
    )
    send_mail(
        subject="Your Login Verification Code",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
