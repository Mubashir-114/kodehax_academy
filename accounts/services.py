import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import salted_hmac


LOGIN_OTP_SESSION_KEY = "login_otp_state"
EMAIL_VERIFICATION_SESSION_KEY = "email_verification_state"
LOGIN_2FA_REAUTH_SESSION_KEY = "login_2fa_recent_otp_at"
LOGIN_OTP_LENGTH = 6
LOGIN_OTP_TTL_SECONDS = getattr(settings, "LOGIN_OTP_TTL_SECONDS", 300)
LOGIN_OTP_RESEND_COOLDOWN_SECONDS = getattr(settings, "LOGIN_OTP_RESEND_COOLDOWN_SECONDS", 30)
LOGIN_OTP_MAX_ATTEMPTS = getattr(settings, "LOGIN_OTP_MAX_ATTEMPTS", 5)
EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS = getattr(
    settings, "EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS", 30
)

# Login 2FA (OTP) policy. Keep the day bounds in sync with users.models.
LOGIN_2FA_MODE_EVERY_LOGIN = "every_login"
LOGIN_2FA_MODE_INTERVAL = "interval"
LOGIN_2FA_MODE_INACTIVITY = "inactivity"
LOGIN_2FA_DEFAULT_DAYS = 1
LOGIN_2FA_MIN_DAYS = 1
LOGIN_2FA_MAX_DAYS = 90
LOGIN_2FA_REAUTH_WINDOW_SECONDS = 10 * 60


def clamp_login_2fa_days(value):
    """Coerce a stored/configured day value into the supported 1-90 range."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return LOGIN_2FA_DEFAULT_DAYS
    if days < LOGIN_2FA_MIN_DAYS:
        return LOGIN_2FA_MIN_DAYS
    if days > LOGIN_2FA_MAX_DAYS:
        return LOGIN_2FA_MAX_DAYS
    return days


def is_login_2fa_policy_weaker(current, proposed):
    """Return whether ``proposed`` relaxes the signed-in user's 2FA policy."""
    if not current["login_2fa_enabled"]:
        return False
    if not proposed["login_2fa_enabled"]:
        return True

    current_mode = current["login_2fa_mode"]
    proposed_mode = proposed["login_2fa_mode"]
    if current_mode == LOGIN_2FA_MODE_EVERY_LOGIN:
        return proposed_mode != LOGIN_2FA_MODE_EVERY_LOGIN
    if proposed_mode == LOGIN_2FA_MODE_EVERY_LOGIN:
        return False
    if current_mode != proposed_mode:
        # Interval and inactivity use different clocks and are not strictly
        # ordered, so require re-authentication for either switch.
        return True
    return proposed["login_2fa_days"] > current["login_2fa_days"]


def has_recent_login_2fa_otp(session, now=None):
    """Check the server-stored timestamp of a successful OTP in this session."""
    verified_at = session.get(LOGIN_2FA_REAUTH_SESSION_KEY)
    if not isinstance(verified_at, int):
        return False
    if now is None:
        now = now_timestamp()
    elapsed = now - verified_at
    return 0 <= elapsed <= LOGIN_2FA_REAUTH_WINDOW_SECONDS


def should_require_login_otp(user, now=None):
    """Decide whether login OTP/2FA should be required for ``user``.

    This is the single source of truth for login OTP timing and must be called
    BEFORE Django's ``login()`` runs, because ``login()`` updates ``last_login``.

    Rules:
      * disabled         -> never require OTP.
      * every_login      -> always require OTP.
      * interval         -> require when there is no previous OTP, or when
                            ``now - last_otp_verified_at`` reaches the interval.
      * inactivity       -> require when there is no previous OTP, no previous
                            successful login, or the time since the previous
                            successful login reaches the threshold.

    Missing/invalid values fall back to the safe default (require OTP).
    """
    if user is None:
        return True
    if not getattr(user, "login_2fa_enabled", True):
        return False
    if now is None:
        now = timezone.now()

    mode = getattr(user, "login_2fa_mode", LOGIN_2FA_MODE_INTERVAL) or LOGIN_2FA_MODE_INTERVAL
    days = clamp_login_2fa_days(getattr(user, "login_2fa_days", LOGIN_2FA_DEFAULT_DAYS))
    threshold = timedelta(days=days)
    last_otp = getattr(user, "last_otp_verified_at", None)

    if mode == LOGIN_2FA_MODE_EVERY_LOGIN:
        return True

    if mode == LOGIN_2FA_MODE_INACTIVITY:
        if not last_otp:
            return True
        last_login = getattr(user, "last_login", None)
        if not last_login:
            return True
        return (now - last_login) >= threshold

    # interval (also the fallback for any unexpected mode value)
    if not last_otp:
        return True
    return (now - last_otp) >= threshold


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
