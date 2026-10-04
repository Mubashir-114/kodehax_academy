from contextlib import nullcontext
from unittest.mock import patch

import requests
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.email_backends import BREVO_EMAIL_URL, BrevoEmailError
from accounts.forms import StudentRegistrationForm
from kodehax_academy.settings import choose_email_backend
from accounts.services import EMAIL_VERIFICATION_SESSION_KEY, now_timestamp
from users.models import User


@override_settings(
    EMAIL_BACKEND="accounts.email_backends.BrevoEmailBackend",
    BREVO_API_KEY="test-api-key",
    BREVO_SENDER_EMAIL="verified-sender@example.com",
    BREVO_SENDER_NAME="Kodehax Sender",
    BREVO_API_TIMEOUT=4.5,
)
class BrevoEmailBackendTests(TestCase):
    @patch("accounts.email_backends.requests.post")
    def test_request_uses_brevo_url_headers_payload_sender_and_timeout(self, post):
        post.return_value.raise_for_status.return_value = None

        sent = EmailMessage(
            subject="Test subject",
            body="Plain body",
            from_email="ignored@example.com",
            to=["student@example.com"],
        ).send()

        self.assertEqual(sent, 1)
        post.assert_called_once_with(
            BREVO_EMAIL_URL,
            headers={
                "accept": "application/json",
                "api-key": "test-api-key",
                "content-type": "application/json",
            },
            json={
                "sender": {
                    "email": "verified-sender@example.com",
                    "name": "Kodehax Sender",
                },
                "to": [{"email": "student@example.com"}],
                "subject": "Test subject",
                "textContent": "Plain body",
            },
            timeout=4.5,
        )

    @patch("accounts.email_backends.requests.post")
    def test_api_error_reaches_caller(self, post):
        post.side_effect = requests.Timeout("timed out")

        with self.assertRaises(BrevoEmailError):
            mail.send_mail(
                "Subject",
                "Body",
                "ignored@example.com",
                ["student@example.com"],
                fail_silently=False,
            )


class VerificationRecoveryTests(TestCase):
    password = "CorrectHorseBattery9!"

    def registration_data(self, **overrides):
        data = {
            "username": "newstudent",
            "email": "newstudent@example.com",
            "password1": self.password,
            "password2": self.password,
        }
        data.update(overrides)
        return data

    @patch("accounts.views.send_verification_email")
    def test_registration_sends_synchronously_and_keeps_user_inactive(self, send_email):
        response = self.client.post(reverse("register"), self.registration_data())

        self.assertRedirects(response, reverse("registration_success"))
        user = User.objects.get(email="newstudent@example.com")
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)
        send_email.assert_called_once_with(response.wsgi_request, user)
        self.assertEqual(
            self.client.session[EMAIL_VERIFICATION_SESSION_KEY]["user_id"], user.pk
        )

    @patch("accounts.views.send_verification_email", side_effect=BrevoEmailError("failed"))
    def test_registration_failure_is_visible_and_account_is_recoverable(self, _send_email):
        response = self.client.post(
            reverse("register"), self.registration_data(), follow=True
        )

        user = User.objects.get(email="newstudent@example.com")
        self.assertFalse(user.is_active)
        self.assertContains(response, "verification email could not be sent")
        self.assertContains(response, reverse("resend_verification"))
        self.assertLessEqual(
            self.client.session[EMAIL_VERIFICATION_SESSION_KEY]["resend_available_at"],
            now_timestamp(),
        )

    @patch("accounts.views.send_verification_email")
    def test_resend_delivers_then_enforces_thirty_second_cooldown(self, send_email):
        user = User.objects.create_user(
            username="pending",
            email="pending@example.com",
            password=self.password,
            role="student",
            is_active=False,
            is_email_verified=False,
        )
        self.client.post(
            reverse("student_login"),
            {"username": user.email, "password": self.password},
        )

        first = self.client.post(reverse("resend_verification"))
        self.assertEqual(first.status_code, 200)
        send_email.assert_called_once_with(first.wsgi_request, user)
        state = self.client.session[EMAIL_VERIFICATION_SESSION_KEY]
        self.assertGreaterEqual(state["resend_available_at"], now_timestamp() + 29)

        second = self.client.post(reverse("resend_verification"))
        self.assertContains(second, "Please wait")
        self.assertEqual(send_email.call_count, 1)

    def test_resend_post_is_csrf_protected(self):
        user = User.objects.create_user(
            username="pending",
            email="pending@example.com",
            password=self.password,
            role="student",
            is_active=False,
            is_email_verified=False,
        )
        session = self.client.session
        session[EMAIL_VERIFICATION_SESSION_KEY] = {
            "user_id": user.pk,
            "resend_available_at": 0,
        }
        session.save()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_session = csrf_client.session
        csrf_session[EMAIL_VERIFICATION_SESSION_KEY] = session[EMAIL_VERIFICATION_SESSION_KEY]
        csrf_session.save()

        response = csrf_client.post(reverse("resend_verification"))

        self.assertEqual(response.status_code, 403)

    def test_resend_page_has_mobile_template(self):
        user = User.objects.create_user(
            username="pending",
            email="pending@example.com",
            password=self.password,
            role="student",
            is_active=False,
            is_email_verified=False,
        )
        session = self.client.session
        session[EMAIL_VERIFICATION_SESSION_KEY] = {
            "user_id": user.pk,
            "email_hint": "pe*****@example.com",
            "resend_available_at": 0,
        }
        session.save()

        response = self.client.get(
            reverse("resend_verification"), HTTP_USER_AGENT="Mozilla/5.0 Mobile"
        )

        self.assertTemplateUsed(response, "mobile/auth/resend_verification.html")

    def test_correct_password_recovers_existing_unverified_account(self):
        user = User.objects.create_user(
            username="pending",
            email="pending@example.com",
            password=self.password,
            role="student",
            is_active=False,
            is_email_verified=False,
        )

        response = self.client.post(
            reverse("student_login"),
            {"username": user.email, "password": self.password},
        )

        self.assertRedirects(response, reverse("resend_verification"))
        self.assertEqual(
            self.client.session[EMAIL_VERIFICATION_SESSION_KEY]["user_id"], user.pk
        )

    @patch("accounts.views.send_verification_email")
    def test_duplicate_email_does_not_create_or_disclose_account(self, send_email):
        User.objects.create_user(
            username="existing",
            email="existing@example.com",
            password=self.password,
            role="student",
            is_active=True,
            is_email_verified=True,
        )

        response = self.client.post(
            reverse("register"),
            self.registration_data(email="existing@example.com", username="different"),
        )

        self.assertRedirects(response, reverse("registration_success"))
        self.assertEqual(User.objects.filter(email__iexact="existing@example.com").count(), 1)
        state = self.client.session[EMAIL_VERIFICATION_SESSION_KEY]
        self.assertNotIn("user_id", state)
        self.assertEqual(state["email_hint"], "ex******@example.com")
        send_email.assert_not_called()


class VerificationReliabilityFixTests(TestCase):
    """Regression coverage for the signup / verification reliability fixes."""

    password = "CorrectHorseBattery9!"

    def _data(self, **overrides):
        data = {
            "username": "fixstudent",
            "email": "fixstudent@example.com",
            "password1": self.password,
            "password2": self.password,
        }
        data.update(overrides)
        return data

    @patch("accounts.views.send_verification_email", side_effect=BrevoEmailError("boom"))
    def test_retry_after_failed_send_actually_resends(self, first_send):
        first = self.client.post(reverse("register"), self._data())
        self.assertRedirects(first, reverse("registration_success"), fetch_redirect_response=False)
        user = User.objects.get(email="fixstudent@example.com")
        # A failed send clears the cooldown so an immediate retry is allowed.
        self.assertLessEqual(
            self.client.session[EMAIL_VERIFICATION_SESSION_KEY]["resend_available_at"],
            now_timestamp(),
        )

        with patch("accounts.views.send_verification_email") as retry_send:
            second = self.client.post(reverse("register"), self._data())

        self.assertRedirects(second, reverse("registration_success"), fetch_redirect_response=False)
        retry_send.assert_called_once_with(second.wsgi_request, user)
        state = self.client.session[EMAIL_VERIFICATION_SESSION_KEY]
        self.assertEqual(state["user_id"], user.pk)
        # A confirmed send records the timestamp and restores the cooldown.
        self.assertIn("sent_at", state)
        self.assertGreaterEqual(state["resend_available_at"], now_timestamp() + 29)

    @patch("accounts.views.send_verification_email")
    def test_double_submit_sends_only_once(self, send_email):
        first = self.client.post(reverse("register"), self._data())
        self.assertRedirects(first, reverse("registration_success"), fetch_redirect_response=False)
        self.assertEqual(send_email.call_count, 1)

        # Immediate duplicate submit must debounce instead of sending twice.
        second = self.client.post(reverse("register"), self._data())
        self.assertRedirects(second, reverse("registration_success"), fetch_redirect_response=False)
        self.assertEqual(send_email.call_count, 1)
        self.assertEqual(User.objects.filter(email="fixstudent@example.com").count(), 1)

    @patch("accounts.views.send_verification_email")
    def test_retry_send_failure_does_not_claim_delivery(self, send_email):
        User.objects.create_user(
            username="fixstudent",
            email="fixstudent@example.com",
            password=self.password,
            role="student",
            is_active=False,
            is_email_verified=False,
        )
        send_email.side_effect = BrevoEmailError("boom")

        response = self.client.post(reverse("register"), self._data(), follow=True)

        self.assertContains(response, "could not be sent")
        self.assertNotContains(response, "A new verification link has been sent")
        self.assertLessEqual(
            self.client.session[EMAIL_VERIFICATION_SESSION_KEY]["resend_available_at"],
            now_timestamp(),
        )

    @patch("accounts.views.send_verification_email")
    def test_active_unverified_user_can_receive_resend(self, send_email):
        user = User.objects.create_user(
            username="activeunverified",
            email="activeunverified@example.com",
            password=self.password,
            role="student",
            is_active=True,
            is_email_verified=False,
        )

        login = self.client.post(
            reverse("student_login"),
            {"username": user.email, "password": self.password},
        )
        self.assertRedirects(login, reverse("resend_verification"), fetch_redirect_response=False)
        # The unverified active account must not be authenticated.
        self.assertNotIn("_auth_user_id", self.client.session)

        resend = self.client.post(reverse("resend_verification"))

        self.assertEqual(resend.status_code, 200)
        send_email.assert_called_once_with(resend.wsgi_request, user)
        self.assertContains(resend, "A new verification link has been sent")

    @patch("accounts.views.send_verification_email")
    def test_active_unverified_resend_failure_does_not_claim_delivery(self, send_email):
        user = User.objects.create_user(
            username="activeunverified",
            email="activeunverified@example.com",
            password=self.password,
            role="student",
            is_active=True,
            is_email_verified=False,
        )
        self.client.post(
            reverse("student_login"),
            {"username": user.email, "password": self.password},
        )
        send_email.side_effect = BrevoEmailError("boom")

        response = self.client.post(reverse("resend_verification"), follow=True)

        self.assertContains(response, "send the verification email. Please try again.")
        self.assertNotContains(response, "A new verification link has been sent")

    def _racy_save(self, conflicting_user_kwargs, password):
        def save(form_self, commit=True):
            User.objects.create_user(
                username="fixstudent",
                email="fixstudent@example.com",
                password=password,
                role="student",
                **conflicting_user_kwargs,
            )
            raise IntegrityError("concurrent duplicate")

        return save

    @patch("accounts.views.send_verification_email")
    def test_concurrent_duplicate_registration_is_handled_and_recovers(self, send_email):
        racy = self._racy_save(
            {"is_active": False, "is_email_verified": False}, self.password
        )
        # Model the racing INSERT as committed by another request: disable the
        # view's atomic wrapper so the simulated conflict row is not rolled back.
        with patch("django.db.transaction.atomic", return_value=nullcontext()):
            with patch.object(StudentRegistrationForm, "save", racy):
                response = self.client.post(reverse("register"), self._data())

        self.assertRedirects(response, reverse("registration_success"), fetch_redirect_response=False)
        self.assertEqual(User.objects.filter(email="fixstudent@example.com").count(), 1)
        # The raced account is recoverable, so a verification email is sent.
        send_email.assert_called_once()

    @patch("accounts.views.send_verification_email")
    def test_concurrent_duplicate_nonrecoverable_account_is_decoy(self, send_email):
        racy = self._racy_save(
            {"is_active": True, "is_email_verified": True}, "DifferentPass9!"
        )
        with patch("django.db.transaction.atomic", return_value=nullcontext()):
            with patch.object(StudentRegistrationForm, "save", racy):
                response = self.client.post(reverse("register"), self._data())

        self.assertRedirects(response, reverse("registration_success"), fetch_redirect_response=False)
        send_email.assert_not_called()
        state = self.client.session[EMAIL_VERIFICATION_SESSION_KEY]
        self.assertNotIn("user_id", state)


class EmailBackendSelectionTests(TestCase):
    def test_brevo_selected_when_configured(self):
        self.assertEqual(
            choose_email_backend(production=True, brevo_configured=True),
            "accounts.email_backends.BrevoEmailBackend",
        )

    def test_smtp_fallback_selected_when_configured(self):
        self.assertEqual(
            choose_email_backend(production=True, smtp_configured=True),
            "django.core.mail.backends.smtp.EmailBackend",
        )

    def test_development_defaults_to_console(self):
        self.assertEqual(
            choose_email_backend(production=False),
            "django.core.mail.backends.console.EmailBackend",
        )

    def test_production_never_selects_console_implicitly(self):
        with self.assertRaises(ImproperlyConfigured):
            choose_email_backend(
                production=True, brevo_configured=False, smtp_configured=False
            )

    def test_production_error_names_variables_without_values(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            choose_email_backend(production=True)
        message = str(ctx.exception)
        for name in ("BREVO_API_KEY", "BREVO_SENDER_EMAIL", "BREVO_SENDER_NAME"):
            self.assertIn(name, message)

    def test_explicit_override_wins_even_in_production(self):
        self.assertEqual(
            choose_email_backend(
                production=True,
                override="django.core.mail.backends.console.EmailBackend",
            ),
            "django.core.mail.backends.console.EmailBackend",
        )
