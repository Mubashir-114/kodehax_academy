import re
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.models import TeacherInvitation
from accounts.services import EMAIL_VERIFICATION_SESSION_KEY, LOGIN_OTP_SESSION_KEY
from accounts.tokens import email_verification_token, teacher_invitation_token
from users.models import User


class EmailVerificationFlowTests(TestCase):
    password = "CorrectHorseBattery9!"

    def _registration_data(self):
        return {
            "username": "newstudent",
            "email": "newstudent@example.com",
            "password1": self.password,
            "password2": self.password,
        }

    def _verification_url(self, user, token=None):
        return reverse(
            "verify_email",
            kwargs={
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": token or email_verification_token.make_token(user),
            },
        )

    @patch("accounts.views.send_verification_email")
    def test_registration_link_verifies_on_another_device_without_authenticating(self, _send):
        device_a = Client()
        device_b = Client()

        registration = device_a.post(reverse("register"), self._registration_data())
        self.assertRedirects(registration, reverse("registration_success"))
        user = User.objects.get(username="newstudent")
        self.assertIn(EMAIL_VERIFICATION_SESSION_KEY, device_a.session)
        self.assertNotIn(EMAIL_VERIFICATION_SESSION_KEY, device_b.session)

        response = device_b.get(self._verification_url(user))

        self.assertRedirects(
            response,
            reverse("student_login"),
            fetch_redirect_response=False,
        )
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_email_verified)
        self.assertNotIn("_auth_user_id", device_b.session)
        self.assertIn(
            "Email verified successfully. Please log in to continue.",
            [str(message) for message in get_messages(response.wsgi_request)],
        )

    def test_teacher_invitation_uses_teacher_login_without_authenticating(self):
        invitation = TeacherInvitation.objects.create(email="teacher@example.com")
        invite_url = reverse(
            "teacher_invite_register",
            kwargs={
                "uid": urlsafe_base64_encode(force_bytes(invitation.pk)),
                "token": teacher_invitation_token.make_token(invitation),
            },
        )

        response = self.client.post(
            invite_url,
            {
                "username": "invitedteacher",
                "password1": self.password,
                "password2": self.password,
            },
        )

        self.assertRedirects(
            response,
            reverse("teacher_login"),
            fetch_redirect_response=False,
        )
        teacher = User.objects.get(username="invitedteacher")
        self.assertTrue(teacher.is_active)
        self.assertTrue(teacher.is_email_verified)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_tampered_verification_token_changes_no_account_state(self):
        user = User.objects.create_user(
            username="pending",
            email="pending@example.com",
            password=self.password,
            role="student",
            is_active=False,
            is_email_verified=False,
        )
        token = email_verification_token.make_token(user)
        replacement = "a" if token[-1] != "a" else "b"

        response = self.client.get(self._verification_url(user, token[:-1] + replacement))

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "invalid or expired", status_code=400)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_malformed_and_nonexistent_user_links_are_rejected_identically(self):
        invalid_links = (
            reverse(
                "verify_email",
                kwargs={
                    "uid": urlsafe_base64_encode(force_bytes("not-an-integer")),
                    "token": "malformed-token",
                },
            ),
            reverse(
                "verify_email",
                kwargs={
                    "uid": urlsafe_base64_encode(force_bytes(999999)),
                    "token": "malformed-token",
                },
            ),
        )

        for url in invalid_links:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, "invalid or expired", status_code=400)
                self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(PASSWORD_RESET_TIMEOUT=60)
    def test_expired_verification_token_changes_no_account_state(self):
        user = User.objects.create_user(
            username="expired",
            email="expired@example.com",
            password=self.password,
            role="student",
            is_active=False,
            is_email_verified=False,
        )
        issued_at = datetime(2026, 1, 1, 12, 0, 0)
        with patch.object(email_verification_token, "_now", return_value=issued_at):
            token = email_verification_token.make_token(user)
        with patch.object(
            email_verification_token,
            "_now",
            return_value=issued_at + timedelta(seconds=61),
        ):
            response = self.client.get(self._verification_url(user, token))

        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_already_used_verification_link_is_rejected_safely(self):
        user = User.objects.create_user(
            username="singleuse",
            email="singleuse@example.com",
            password=self.password,
            role="student",
            is_active=False,
            is_email_verified=False,
        )
        url = self._verification_url(user)
        self.assertRedirects(
            self.client.get(url),
            reverse("student_login"),
            fetch_redirect_response=False,
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "invalid or expired", status_code=400)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_email_verified)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_used_link_does_not_reactivate_a_later_deactivated_account(self):
        user = User.objects.create_user(
            username="deactivated",
            email="deactivated@example.com",
            password=self.password,
            role="student",
            is_active=False,
            is_email_verified=False,
        )
        url = self._verification_url(user)
        self.client.get(url)
        User.objects.filter(pk=user.pk).update(is_active=False)

        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertTrue(user.is_email_verified)
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch("accounts.views.send_login_otp_email")
    @patch("accounts.views.generate_login_otp", return_value="123456")
    def test_verified_user_login_requires_and_completes_session_bound_otp(
        self, _generate_otp, send_otp
    ):
        user = User.objects.create_user(
            username="otpstudent",
            email="otpstudent@example.com",
            password=self.password,
            role="student",
            is_active=False,
            is_email_verified=False,
        )
        self.client.get(self._verification_url(user))

        login_response = self.client.post(
            reverse("student_login"),
            {"username": user.email, "password": self.password},
        )

        self.assertRedirects(login_response, reverse("verify_login_otp"))
        send_otp.assert_called_once_with(user, "123456")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn(LOGIN_OTP_SESSION_KEY, self.client.session)

        otp_response = self.client.post(
            reverse("verify_login_otp"),
            {"otp": "123456"},
        )

        self.assertRedirects(
            otp_response,
            reverse("student_dashboard"),
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))
        self.assertNotIn(LOGIN_OTP_SESSION_KEY, self.client.session)

    @patch("accounts.views.send_login_otp_email")
    def test_recently_otp_verified_user_skips_new_otp(self, send_otp):
        user = User.objects.create_user(
            username="recentotp",
            email="recentotp@example.com",
            password=self.password,
            role="student",
            is_active=True,
            is_email_verified=True,
            last_otp_verified_at=timezone.now(),
        )

        response = self.client.post(
            reverse("student_login"),
            {"username": user.username, "password": self.password},
        )

        self.assertRedirects(
            response,
            reverse("student_dashboard"),
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))
        self.assertNotIn(LOGIN_OTP_SESSION_KEY, self.client.session)
        send_otp.assert_not_called()

    @patch("accounts.views.send_login_otp_email")
    def test_verified_user_with_bad_password_stays_unauthenticated(self, send_otp):
        user = User.objects.create_user(
            username="badpassword",
            email="badpassword@example.com",
            password=self.password,
            role="student",
            is_active=True,
            is_email_verified=True,
        )

        response = self.client.post(
            reverse("student_login"),
            {"username": user.email, "password": "wrong-password"},
        )

        self.assertRedirects(response, reverse("student_login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn(LOGIN_OTP_SESSION_KEY, self.client.session)
        send_otp.assert_not_called()


class LoginOTPFlowTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student1",
            email="student1@example.com",
            password="pass12345",
            role="student",
            is_active=True,
            is_email_verified=True,
        )
        self.teacher = User.objects.create_user(
            username="teacher1",
            email="teacher1@example.com",
            password="pass12345",
            role="teacher",
            is_active=True,
            is_email_verified=True,
        )
        self.admin_user = User.objects.create_user(
            username="admin1",
            email="admin1@example.com",
            password="pass12345",
            role="admin",
            is_active=True,
            is_email_verified=True,
            is_superuser=True,
            is_staff=True,
        )

    def _extract_otp(self):
        match = re.search(r"(\d{6})", mail.outbox[-1].body)
        self.assertIsNotNone(match)
        return match.group(1)

    def _pending_state(self):
        return self.client.session.get(LOGIN_OTP_SESSION_KEY)

    def test_student_login_requires_otp_before_session_login(self):
        response = self.client.post(
            reverse("student_login"),
            {"username": "student1@example.com", "password": "pass12345"},
        )

        self.assertRedirects(response, reverse("verify_login_otp"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIsNotNone(self._pending_state())
        self.assertEqual(len(mail.outbox), 1)

        verify_response = self.client.post(reverse("verify_login_otp"), {"otp": self._extract_otp()})

        self.assertRedirects(verify_response, reverse("student_dashboard"), fetch_redirect_response=False)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(self.student.pk))
        self.assertIsNone(self._pending_state())

    def test_teacher_login_requires_otp_and_redirects_to_teacher_dashboard(self):
        response = self.client.post(
            reverse("teacher_login"),
            {"username": "teacher1", "password": "pass12345"},
        )

        self.assertRedirects(response, reverse("verify_login_otp"))
        verify_response = self.client.post(reverse("verify_login_otp"), {"otp": self._extract_otp()})

        self.assertRedirects(verify_response, reverse("teacher_dashboard"))
        self.assertEqual(self.client.session.get("_auth_user_id"), str(self.teacher.pk))

    def test_resend_generates_new_otp_and_invalidates_previous_code(self):
        self.client.post(
            reverse("teacher_login"),
            {"username": "teacher1", "password": "pass12345"},
        )
        original_otp = self._extract_otp()

        session = self.client.session
        state = session[LOGIN_OTP_SESSION_KEY]
        state["resend_available_at"] = int(timezone.now().timestamp()) - 1
        session[LOGIN_OTP_SESSION_KEY] = state
        session.save()

        resend_response = self.client.post(reverse("resend_login_otp"))
        self.assertRedirects(resend_response, reverse("verify_login_otp"))
        self.assertEqual(len(mail.outbox), 2)
        new_otp = self._extract_otp()
        self.assertNotEqual(original_otp, new_otp)

        invalid_response = self.client.post(reverse("verify_login_otp"), {"otp": original_otp})
        self.assertRedirects(invalid_response, reverse("verify_login_otp"))
        self.assertNotIn("_auth_user_id", self.client.session)

        valid_response = self.client.post(reverse("verify_login_otp"), {"otp": new_otp})
        self.assertRedirects(valid_response, reverse("teacher_dashboard"))
        self.assertEqual(self.client.session.get("_auth_user_id"), str(self.teacher.pk))

    def test_expired_otp_is_rejected(self):
        self.client.post(
            reverse("student_login"),
            {"username": "student1", "password": "pass12345"},
        )
        otp = self._extract_otp()

        session = self.client.session
        state = session[LOGIN_OTP_SESSION_KEY]
        state["expires_at"] = int(timezone.now().timestamp()) - 1
        session[LOGIN_OTP_SESSION_KEY] = state
        session.save()

        response = self.client.post(reverse("verify_login_otp"), {"otp": otp})

        self.assertRedirects(response, reverse("verify_login_otp"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIsNotNone(self._pending_state())

    def test_too_many_invalid_attempts_clears_pending_login(self):
        self.client.post(
            reverse("student_login"),
            {"username": "student1", "password": "pass12345"},
        )

        for _ in range(4):
            response = self.client.post(reverse("verify_login_otp"), {"otp": "000000"})
            self.assertRedirects(response, reverse("verify_login_otp"))

        final_response = self.client.post(reverse("verify_login_otp"), {"otp": "000000"})

        self.assertRedirects(final_response, reverse("student_login"))
        self.assertIsNone(self._pending_state())
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch("accounts.views.send_login_otp_email", side_effect=RuntimeError("backend down"))
    def test_otp_send_failure_is_visible_and_never_claims_success(self, _send):
        response = self.client.post(
            reverse("student_login"),
            {"username": "student1@example.com", "password": "pass12345"},
            follow=True,
        )

        self.assertContains(response, "send your verification code right now")
        self.assertNotContains(response, "Verification code sent")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIsNone(self._pending_state())

    def test_admin_teacher_login_bypasses_otp_and_remains_unchanged(self):
        response = self.client.post(
            reverse("teacher_login"),
            {"username": "admin1", "password": "pass12345"},
        )

        self.assertRedirects(response, reverse("adminpanel_dashboard"))
        self.assertEqual(self.client.session.get("_auth_user_id"), str(self.admin_user.pk))
        self.assertIsNone(self._pending_state())
        self.assertEqual(len(mail.outbox), 0)
