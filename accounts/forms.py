import logging
import threading

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)

from .models import TeacherInvitation
from .tokens import email_verification_token, teacher_invitation_token

User = get_user_model()


INPUT_CLASS = (
    "w-full rounded-2xl border border-slate-700/80 bg-slate-950/70 px-4 py-3 "
    "text-slate-100 placeholder:text-slate-500 focus:border-cyan-400 "
    "focus:outline-none focus:ring-2 focus:ring-cyan-400/30"
)
ADMIN_INPUT_CLASS = "w-full rounded-xl border border-slate-300 px-3 py-2 text-slate-900"


class StyledFormMixin:
    def _apply_classes(self):
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT_CLASS)


class StudentRegistrationForm(StyledFormMixin, forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Create password"}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Confirm password"}))

    class Meta:
        model = User
        fields = ("username", "email")
        widgets = {
            "username": forms.TextInput(attrs={"placeholder": "Choose a username"}),
            "email": forms.EmailInput(attrs={"placeholder": "you@example.com"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        if password1:
            self.instance.username = cleaned_data.get("username", "")
            self.instance.email = cleaned_data.get("email", "")
            try:
                password_validation.validate_password(password1, self.instance)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.role = "student"
        user.is_active = False
        user.is_email_verified = False
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class LoginForm(StyledFormMixin, forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={"placeholder": "Email or username"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Password"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()


class LoginOTPForm(StyledFormMixin, forms.Form):
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter 6-digit OTP",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "pattern": "[0-9]*",
                "maxlength": "6",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()

    def clean_otp(self):
        otp = "".join(ch for ch in self.cleaned_data["otp"].strip() if ch.isdigit())
        if len(otp) != 6:
            raise forms.ValidationError("Enter the 6-digit code sent to your email.")
        return otp


class ForgotPasswordForm(StyledFormMixin, forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "Enter your registered email"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_classes()

    def clean_email(self):
        return self.cleaned_data["email"].lower().strip()


class ResetPasswordForm(StyledFormMixin, forms.Form):
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "New password"}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Confirm new password"}))

    def __init__(self, user=None, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self._apply_classes()

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        if password1:
            try:
                password_validation.validate_password(password1, self.user)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned_data


class ProfilePasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    old_password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Current password"}))
    new_password1 = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "New password"}))
    new_password2 = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Confirm new password"}))

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self._apply_classes()


class TeacherInvitationAdminForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = TeacherInvitation
        fields = ("email",)
        widgets = {
            "email": forms.EmailInput(attrs={"placeholder": "teacher@kodehax.com"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs["class"] = ADMIN_INPUT_CLASS

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def validate_unique(self):
        # Invitations are upserted in save(), so an existing invitation email
        # should not raise the ModelForm unique-field error here.
        return

    def save(self, request, commit=True):
        with transaction.atomic():
            invitation, created = TeacherInvitation.objects.update_or_create(
                email=self.cleaned_data["email"],
                defaults={
                    "token": "",
                    "is_used": False,
                    "invited_by": request.user,
                    "used_at": None,
                },
            )
            if commit:
                invitation.save()
            self.send_email(request, invitation)
        invitation.was_created = created
        return invitation

    def send_email(self, request, invitation):
        uid = urlsafe_base64_encode(force_bytes(invitation.pk))
        token = teacher_invitation_token.make_token(invitation)
        invite_url = request.build_absolute_uri(
            reverse("teacher_invite_register", kwargs={"uid": uid, "token": token})
        )
        message = render_to_string(
            "accounts/email/teacher_invitation.txt",
            {
                "invite_url": invite_url,
                "site_name": "Kodehax Academy",
                "expires_hours": getattr(settings, "PASSWORD_RESET_TIMEOUT", 86400) // 3600,
            },
        )
        send_mail(
            subject="Teacher invitation for Kodehax Academy",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            fail_silently=False,
        )


def resend_teacher_invitation(request, invitation):
    with transaction.atomic():
        invitation.is_used = False
        invitation.used_at = None
        invitation.invited_by = request.user
        invitation.refresh_token()
        invitation.save(update_fields=["token", "is_used", "used_at", "invited_by"])
        TeacherInvitationAdminForm().send_email(request, invitation)
    return invitation


class TeacherInviteRegistrationForm(StyledFormMixin, forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={"placeholder": "Choose a username"}))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Create password"}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Confirm password"}))

    def __init__(self, invitation=None, *args, **kwargs):
        self.invitation = invitation
        super().__init__(*args, **kwargs)
        self._apply_classes()

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        dummy_user = User(username=cleaned_data.get("username", ""), email=getattr(self.invitation, "email", ""), role="teacher")
        if password1:
            try:
                password_validation.validate_password(password1, dummy_user)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned_data

    def save(self):
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.invitation.email,
            password=self.cleaned_data["password1"],
            role="teacher",
            is_active=True,
            is_email_verified=True,
        )
        self.invitation.is_used = True
        self.invitation.used_at = timezone.now()
        self.invitation.save(update_fields=["is_used", "used_at"])
        self.invitation.delete()
        return user


def send_verification_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    verify_url = request.build_absolute_uri(reverse("verify_email", kwargs={"uid": uid, "token": token}))
    message = render_to_string(
        "accounts/email/verify_email.txt",
        {
            "user": user,
            "verify_url": verify_url,
            "site_name": "Kodehax Academy",
        },
    )

    return send_mail(
        subject="Verify your Kodehax Academy email",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def send_password_reset_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = request.build_absolute_uri(reverse("reset_password", kwargs={"uid": uid, "token": token}))
    message = render_to_string(
        "accounts/email/reset_password.txt",
        {
            "user": user,
            "reset_url": reset_url,
            "site_name": "Kodehax Academy",
        },
    )

    def _send():
        try:
            send_mail(
                subject="Reset your Kodehax Academy password",
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception:
            logger.exception("Failed to send password reset email")

    threading.Thread(target=_send, daemon=True).start()
