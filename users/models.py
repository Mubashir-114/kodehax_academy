# Create your models here.
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


# Valid range for the login 2FA interval/inactivity threshold, in days.
# These literals are also mirrored in accounts.services (policy helper) and are
# serialized into the migration, so keep them in sync when changing bounds.
LOGIN_2FA_MIN_DAYS = 1
LOGIN_2FA_MAX_DAYS = 90


class User(AbstractUser):

    ROLE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('admin', 'Admin'),
    )

    class Login2FAMode(models.TextChoices):
        EVERY_LOGIN = "every_login", "Every login"
        INTERVAL = "interval", "Every N days"
        INACTIVITY = "inactivity", "After inactivity"

    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    is_email_verified = models.BooleanField(default=False)
    last_otp_verified_at = models.DateTimeField(null=True, blank=True)

    # Login 2FA (OTP) policy. Defaults preserve the previous behaviour: OTP is
    # required once every 24 hours (interval, 1 day).
    login_2fa_enabled = models.BooleanField(default=True)
    login_2fa_mode = models.CharField(
        max_length=20,
        choices=Login2FAMode.choices,
        default=Login2FAMode.INTERVAL,
    )
    login_2fa_days = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(LOGIN_2FA_MIN_DAYS), MaxValueValidator(LOGIN_2FA_MAX_DAYS)],
    )

    def __str__(self):
        return self.username
