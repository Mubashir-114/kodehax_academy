import re
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.services import LOGIN_OTP_SESSION_KEY
from users.models import User


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
