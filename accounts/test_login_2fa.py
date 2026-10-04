from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.forms import LoginSecurityForm
from accounts.services import (
    LOGIN_2FA_REAUTH_SESSION_KEY,
    has_recent_login_2fa_otp,
    is_login_2fa_policy_weaker,
    should_require_login_otp,
)
from users.models import User


class ShouldRequireLoginOtpPolicyTests(SimpleTestCase):
    """Unit coverage for the centralized login-2FA policy helper."""

    def _user(self, **overrides):
        base = {
            "login_2fa_enabled": True,
            "login_2fa_mode": "interval",
            "login_2fa_days": 1,
            "last_otp_verified_at": None,
            "last_login": None,
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_disabled_never_requires_otp(self):
        user = self._user(login_2fa_enabled=False)
        self.assertFalse(should_require_login_otp(user))

    def test_every_login_always_requires_otp_even_when_recent(self):
        user = self._user(
            login_2fa_mode="every_login",
            last_otp_verified_at=timezone.now(),
        )
        self.assertTrue(should_require_login_otp(user))

    def test_interval_without_previous_otp_requires_otp(self):
        self.assertTrue(should_require_login_otp(self._user()))

    def test_interval_within_threshold_skips_otp(self):
        now = timezone.now()
        user = self._user(last_otp_verified_at=now - timedelta(hours=23))
        self.assertFalse(should_require_login_otp(user, now=now))

    def test_interval_at_or_after_threshold_requires_otp(self):
        now = timezone.now()
        self.assertTrue(
            should_require_login_otp(
                self._user(last_otp_verified_at=now - timedelta(days=1)), now=now
            )
        )
        self.assertTrue(
            should_require_login_otp(
                self._user(last_otp_verified_at=now - timedelta(days=5)), now=now
            )
        )

    def test_two_and_three_day_intervals(self):
        now = timezone.now()
        two_day = self._user(login_2fa_days=2, last_otp_verified_at=now - timedelta(days=1))
        self.assertFalse(should_require_login_otp(two_day, now=now))
        two_day_expired = self._user(
            login_2fa_days=2, last_otp_verified_at=now - timedelta(days=2)
        )
        self.assertTrue(should_require_login_otp(two_day_expired, now=now))

        three_day = self._user(
            login_2fa_days=3, last_otp_verified_at=now - timedelta(days=2)
        )
        self.assertFalse(should_require_login_otp(three_day, now=now))
        three_day_expired = self._user(
            login_2fa_days=3, last_otp_verified_at=now - timedelta(days=3)
        )
        self.assertTrue(should_require_login_otp(three_day_expired, now=now))

    def test_custom_valid_interval(self):
        now = timezone.now()
        within = self._user(login_2fa_days=45, last_otp_verified_at=now - timedelta(days=44))
        self.assertFalse(should_require_login_otp(within, now=now))
        expired = self._user(login_2fa_days=45, last_otp_verified_at=now - timedelta(days=45))
        self.assertTrue(should_require_login_otp(expired, now=now))

    def test_invalid_day_values_are_clamped_safely(self):
        now = timezone.now()
        # 0/negative clamp to 1 day: a 1-day-old OTP must require.
        for bad in (0, -5, None, "not-a-number"):
            user = self._user(login_2fa_days=bad, last_otp_verified_at=now - timedelta(days=1))
            self.assertTrue(should_require_login_otp(user, now=now), bad)
        # Huge values clamp to 90 days.
        huge = self._user(login_2fa_days=9999, last_otp_verified_at=now - timedelta(days=89))
        self.assertFalse(should_require_login_otp(huge, now=now))
        huge_expired = self._user(
            login_2fa_days=9999, last_otp_verified_at=now - timedelta(days=90)
        )
        self.assertTrue(should_require_login_otp(huge_expired, now=now))

    def test_inactivity_below_threshold_skips_otp(self):
        now = timezone.now()
        user = self._user(
            login_2fa_mode="inactivity",
            login_2fa_days=7,
            last_otp_verified_at=now - timedelta(days=1),
            last_login=now - timedelta(days=3),
        )
        self.assertFalse(should_require_login_otp(user, now=now))

    def test_inactivity_at_or_above_threshold_requires_otp(self):
        now = timezone.now()
        user = self._user(
            login_2fa_mode="inactivity",
            login_2fa_days=7,
            last_otp_verified_at=now - timedelta(days=1),
            last_login=now - timedelta(days=7),
        )
        self.assertTrue(should_require_login_otp(user, now=now))

    def test_inactivity_without_previous_login_requires_otp(self):
        now = timezone.now()
        user = self._user(
            login_2fa_mode="inactivity",
            login_2fa_days=7,
            last_otp_verified_at=now - timedelta(hours=1),
            last_login=None,
        )
        self.assertTrue(should_require_login_otp(user, now=now))

    def test_inactivity_without_previous_otp_requires_otp(self):
        now = timezone.now()
        user = self._user(
            login_2fa_mode="inactivity",
            login_2fa_days=7,
            last_otp_verified_at=None,
            last_login=now - timedelta(days=1),
        )
        self.assertTrue(should_require_login_otp(user, now=now))

    def test_objects_missing_policy_attributes_default_to_strict_interval(self):
        # Old/other user objects without the new fields behave like the previous
        # 1-day interval policy: require OTP when there is no prior verification.
        legacy = SimpleNamespace(last_otp_verified_at=None, last_login=None)
        self.assertTrue(should_require_login_otp(legacy))
        recent = SimpleNamespace(
            last_otp_verified_at=timezone.now() - timedelta(hours=1), last_login=None
        )
        self.assertFalse(should_require_login_otp(recent))


class Login2FAReauthenticationPolicyTests(SimpleTestCase):
    def test_stricter_transitions_do_not_count_as_weaker(self):
        current = {"login_2fa_enabled": False, "login_2fa_mode": "interval", "login_2fa_days": 7}
        self.assertFalse(
            is_login_2fa_policy_weaker(
                current,
                {"login_2fa_enabled": True, "login_2fa_mode": "interval", "login_2fa_days": 7},
            )
        )

        current = {"login_2fa_enabled": True, "login_2fa_mode": "interval", "login_2fa_days": 14}
        self.assertFalse(
            is_login_2fa_policy_weaker(
                current,
                {"login_2fa_enabled": True, "login_2fa_mode": "every_login", "login_2fa_days": 1},
            )
        )
        self.assertFalse(
            is_login_2fa_policy_weaker(
                current,
                {"login_2fa_enabled": True, "login_2fa_mode": "interval", "login_2fa_days": 7},
            )
        )

    def test_weaker_transitions_require_reauthentication(self):
        current = {"login_2fa_enabled": True, "login_2fa_mode": "every_login", "login_2fa_days": 1}
        self.assertTrue(
            is_login_2fa_policy_weaker(
                current,
                {"login_2fa_enabled": False, "login_2fa_mode": "every_login", "login_2fa_days": 1},
            )
        )
        self.assertTrue(
            is_login_2fa_policy_weaker(
                current,
                {"login_2fa_enabled": True, "login_2fa_mode": "interval", "login_2fa_days": 1},
            )
        )

        current = {"login_2fa_enabled": True, "login_2fa_mode": "interval", "login_2fa_days": 7}
        self.assertTrue(
            is_login_2fa_policy_weaker(
                current,
                {"login_2fa_enabled": True, "login_2fa_mode": "interval", "login_2fa_days": 14},
            )
        )
        self.assertTrue(
            is_login_2fa_policy_weaker(
                current,
                {"login_2fa_enabled": True, "login_2fa_mode": "inactivity", "login_2fa_days": 1},
            )
        )

    def test_recent_otp_session_marker_obeys_trusted_window(self):
        now = int(timezone.now().timestamp())
        self.assertTrue(
            has_recent_login_2fa_otp({LOGIN_2FA_REAUTH_SESSION_KEY: now - 600}, now=now)
        )
        self.assertFalse(
            has_recent_login_2fa_otp({LOGIN_2FA_REAUTH_SESSION_KEY: now - 601}, now=now)
        )
        self.assertFalse(
            has_recent_login_2fa_otp({LOGIN_2FA_REAUTH_SESSION_KEY: now + 1}, now=now)
        )
        self.assertFalse(has_recent_login_2fa_otp({}, now=now))


class LoginSecurityFormTests(TestCase):
    password = "CorrectHorseBattery9!"

    def _user(self, **overrides):
        defaults = dict(
            username="secstudent",
            email="secstudent@example.com",
            password=self.password,
            role="student",
            is_active=True,
            is_email_verified=True,
        )
        defaults.update(overrides)
        return User.objects.create_user(**defaults)

    def test_migrated_defaults_preserve_one_day_interval(self):
        user = self._user()
        self.assertTrue(user.login_2fa_enabled)
        self.assertEqual(user.login_2fa_mode, User.Login2FAMode.INTERVAL)
        self.assertEqual(user.login_2fa_days, 1)

    def test_custom_valid_interval_is_saved(self):
        user = self._user()
        form = LoginSecurityForm(
            data={"login_2fa_enabled": "on", "login_2fa_mode": "interval", "login_2fa_days": "45"},
            instance=user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()
        self.assertEqual(user.login_2fa_days, 45)
        self.assertEqual(user.login_2fa_mode, "interval")

    def test_every_login_normalizes_days(self):
        user = self._user()
        form = LoginSecurityForm(
            data={"login_2fa_enabled": "on", "login_2fa_mode": "every_login", "login_2fa_days": "45"},
            instance=user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()
        self.assertEqual(user.login_2fa_days, 1)

    def test_invalid_custom_intervals_are_rejected(self):
        for bad in ("0", "-3", "91", "100000"):
            with self.subTest(bad=bad):
                user = self._user(username=f"bad{bad}".replace("-", "n"), email=f"bad{bad}@example.com".replace("-", "n"))
                form = LoginSecurityForm(
                    data={
                        "login_2fa_enabled": "on",
                        "login_2fa_mode": "interval",
                        "login_2fa_days": bad,
                    },
                    instance=user,
                )
                self.assertFalse(form.is_valid())
                self.assertIn("login_2fa_days", form.errors)

    def test_non_numeric_custom_interval_is_rejected(self):
        user = self._user()
        form = LoginSecurityForm(
            data={"login_2fa_enabled": "on", "login_2fa_mode": "interval", "login_2fa_days": "abc"},
            instance=user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("login_2fa_days", form.errors)

    def test_disabled_persists_without_touching_last_otp(self):
        verified_at = timezone.now() - timedelta(days=3)
        user = self._user(last_otp_verified_at=verified_at)
        form = LoginSecurityForm(
            data={"login_2fa_mode": "interval", "login_2fa_days": "2"},
            instance=user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()
        self.assertFalse(user.login_2fa_enabled)
        self.assertEqual(user.last_otp_verified_at, verified_at)


class LoginSecurityViewTests(TestCase):
    password = "CorrectHorseBattery9!"

    def setUp(self):
        self.user = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password=self.password,
            role="student",
            is_active=True,
            is_email_verified=True,
        )
        self.other = User.objects.create_user(
            username="other",
            email="other@example.com",
            password=self.password,
            role="student",
            is_active=True,
            is_email_verified=True,
            login_2fa_enabled=False,
            login_2fa_mode="every_login",
            login_2fa_days=30,
        )

    def test_view_persists_own_settings(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("update_login_security"),
            {
                "login_2fa_enabled": "on",
                "login_2fa_mode": "inactivity",
                "login_2fa_days": "14",
                "current_password": self.password,
            },
        )
        self.assertRedirects(response, reverse("student_profile"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.login_2fa_enabled)
        self.assertEqual(self.user.login_2fa_mode, "inactivity")
        self.assertEqual(self.user.login_2fa_days, 14)

    def test_view_invalid_input_leaves_settings_unchanged(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("update_login_security"),
            {"login_2fa_enabled": "on", "login_2fa_mode": "interval", "login_2fa_days": "0"},
        )
        self.assertRedirects(response, reverse("student_profile"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.login_2fa_days, 1)

    def test_view_cannot_modify_another_user(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("update_login_security"),
            {
                "user_id": self.other.pk,
                "id": self.other.pk,
                "username": self.other.username,
                "login_2fa_enabled": "on",
                "login_2fa_mode": "interval",
                "login_2fa_days": "5",
                "current_password": self.password,
            },
        )
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.user.login_2fa_mode, "interval")
        self.assertEqual(self.user.login_2fa_days, 5)
        # The other account must be untouched.
        self.assertFalse(self.other.login_2fa_enabled)
        self.assertEqual(self.other.login_2fa_mode, "every_login")
        self.assertEqual(self.other.login_2fa_days, 30)

    def test_get_does_not_change_settings(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("update_login_security"))
        self.assertRedirects(response, reverse("student_profile"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.login_2fa_days, 1)

    def test_stronger_enable_mode_and_frequency_changes_save_without_password(self):
        self.user.login_2fa_enabled = False
        self.user.save(update_fields=["login_2fa_enabled"])
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("update_login_security"),
            {"login_2fa_enabled": "on", "login_2fa_mode": "interval", "login_2fa_days": "14"},
        )
        self.assertRedirects(response, reverse("student_profile"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.login_2fa_enabled)
        self.assertEqual(self.user.login_2fa_days, 14)

        self.client.post(
            reverse("update_login_security"),
            {"login_2fa_enabled": "on", "login_2fa_mode": "every_login", "login_2fa_days": "1"},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.login_2fa_mode, "every_login")

        self.user.login_2fa_mode = "interval"
        self.user.login_2fa_days = 14
        self.user.save(update_fields=["login_2fa_mode", "login_2fa_days"])
        self.client.post(
            reverse("update_login_security"),
            {"login_2fa_enabled": "on", "login_2fa_mode": "interval", "login_2fa_days": "7"},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.login_2fa_days, 7)

    def test_weaker_disable_requires_password_and_rejects_invalid_password(self):
        self.client.force_login(self.user)
        url = reverse("update_login_security")
        data = {"login_2fa_mode": "interval", "login_2fa_days": "1"}

        with self.assertLogs("accounts.views", level="INFO") as captured:
            response = self.client.post(url, data)
        self.assertTrue(
            any("reason=reauth_required" in entry for entry in captured.output),
            captured.output,
        )
        self.assertRedirects(
            response, f"{reverse('student_profile')}?reauth=1", fetch_redirect_response=False
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.login_2fa_enabled)

        response = self.client.post(url, {**data, "current_password": "incorrect"})
        self.assertRedirects(
            response, f"{reverse('student_profile')}?reauth=1", fetch_redirect_response=False
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.login_2fa_enabled)

        response = self.client.post(url, {**data, "current_password": self.password})
        self.assertRedirects(response, reverse("student_profile"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertFalse(self.user.login_2fa_enabled)

    def test_weaker_schedule_changes_require_password_or_recent_otp(self):
        self.user.login_2fa_mode = "interval"
        self.user.login_2fa_days = 7
        self.user.save(update_fields=["login_2fa_mode", "login_2fa_days"])
        self.client.force_login(self.user)
        url = reverse("update_login_security")
        increase_days = {
            "login_2fa_enabled": "on",
            "login_2fa_mode": "interval",
            "login_2fa_days": "14",
        }

        response = self.client.post(url, increase_days)
        self.assertRedirects(
            response, f"{reverse('student_profile')}?reauth=1", fetch_redirect_response=False
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.login_2fa_days, 7)

        session = self.client.session
        session[LOGIN_2FA_REAUTH_SESSION_KEY] = int(timezone.now().timestamp())
        session.save()
        response = self.client.post(url, increase_days)
        self.assertRedirects(response, reverse("student_profile"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.login_2fa_days, 14)

    def test_every_login_to_interval_requires_reauthentication(self):
        self.user.login_2fa_mode = "every_login"
        self.user.save(update_fields=["login_2fa_mode"])
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("update_login_security"),
            {"login_2fa_enabled": "on", "login_2fa_mode": "interval", "login_2fa_days": "1"},
        )
        self.assertRedirects(
            response, f"{reverse('student_profile')}?reauth=1", fetch_redirect_response=False
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.login_2fa_mode, "every_login")

    def test_stale_otp_session_cannot_authorize_weaker_change(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[LOGIN_2FA_REAUTH_SESSION_KEY] = int(
            (timezone.now() - timedelta(minutes=11)).timestamp()
        )
        session.save()

        response = self.client.post(
            reverse("update_login_security"),
            {"login_2fa_mode": "interval", "login_2fa_days": "1"},
        )
        self.assertRedirects(
            response, f"{reverse('student_profile')}?reauth=1", fetch_redirect_response=False
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.login_2fa_enabled)


class LoginFlowPolicyIntegrationTests(TestCase):
    password = "CorrectHorseBattery9!"

    def _verified_user(self, **overrides):
        defaults = dict(
            username="flowuser",
            email="flowuser@example.com",
            password=self.password,
            role="student",
            is_active=True,
            is_email_verified=True,
        )
        defaults.update(overrides)
        return User.objects.create_user(**defaults)

    def _login(self, user):
        return self.client.post(
            reverse("student_login"),
            {"username": user.email, "password": self.password},
        )

    @patch("accounts.views.send_login_otp_email")
    def test_2fa_disabled_logs_in_without_otp(self, send_otp):
        user = self._verified_user(login_2fa_enabled=False, last_otp_verified_at=None)
        response = self._login(user)
        self.assertRedirects(response, reverse("student_dashboard"), fetch_redirect_response=False)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))
        send_otp.assert_not_called()

    @patch("accounts.views.send_login_otp_email")
    def test_disabled_2fa_does_not_bypass_email_verification(self, send_otp):
        user = self._verified_user(
            username="unverified",
            email="unverified@example.com",
            is_active=False,
            is_email_verified=False,
            login_2fa_enabled=False,
        )
        response = self._login(user)
        self.assertRedirects(response, reverse("resend_verification"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        send_otp.assert_not_called()

    @patch("accounts.views.generate_login_otp", return_value="123456")
    @patch("accounts.views.send_login_otp_email")
    def test_every_login_requires_otp_each_time(self, send_otp, _gen):
        user = self._verified_user(
            login_2fa_mode="every_login",
            last_otp_verified_at=timezone.now(),
        )
        response = self._login(user)
        self.assertRedirects(response, reverse("verify_login_otp"))
        send_otp.assert_called_once()
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch("accounts.views.send_login_otp_email")
    def test_interval_within_threshold_skips_otp(self, send_otp):
        user = self._verified_user(
            login_2fa_mode="interval",
            login_2fa_days=3,
            last_otp_verified_at=timezone.now() - timedelta(days=1),
        )
        response = self._login(user)
        self.assertRedirects(response, reverse("student_dashboard"), fetch_redirect_response=False)
        send_otp.assert_not_called()

    @patch("accounts.views.generate_login_otp", return_value="123456")
    @patch("accounts.views.send_login_otp_email")
    def test_interval_after_threshold_requires_otp(self, send_otp, _gen):
        user = self._verified_user(
            login_2fa_mode="interval",
            login_2fa_days=3,
            last_otp_verified_at=timezone.now() - timedelta(days=3),
        )
        response = self._login(user)
        self.assertRedirects(response, reverse("verify_login_otp"))
        send_otp.assert_called_once()

    @patch("accounts.views.generate_login_otp", return_value="123456")
    @patch("accounts.views.send_login_otp_email")
    def test_inactivity_no_previous_login_requires_otp(self, send_otp, _gen):
        user = self._verified_user(
            login_2fa_mode="inactivity",
            login_2fa_days=7,
            last_otp_verified_at=timezone.now(),
            last_login=None,
        )
        response = self._login(user)
        self.assertRedirects(response, reverse("verify_login_otp"))
        send_otp.assert_called_once()

    @patch("accounts.views.send_login_otp_email")
    def test_inactivity_within_threshold_skips_otp(self, send_otp):
        user = self._verified_user(
            login_2fa_mode="inactivity",
            login_2fa_days=10,
            last_otp_verified_at=timezone.now() - timedelta(days=1),
            last_login=timezone.now() - timedelta(days=2),
        )
        response = self._login(user)
        self.assertRedirects(response, reverse("student_dashboard"), fetch_redirect_response=False)
        send_otp.assert_not_called()

    @patch("accounts.views.generate_login_otp", return_value="123456")
    @patch("accounts.views.send_login_otp_email")
    def test_inactivity_after_threshold_requires_otp(self, send_otp, _gen):
        user = self._verified_user(
            login_2fa_mode="inactivity",
            login_2fa_days=10,
            last_otp_verified_at=timezone.now() - timedelta(days=1),
            last_login=timezone.now() - timedelta(days=10),
        )
        response = self._login(user)
        self.assertRedirects(response, reverse("verify_login_otp"))
        send_otp.assert_called_once()

    @patch("accounts.views.generate_login_otp", return_value="123456")
    @patch("accounts.views.send_login_otp_email")
    def test_otp_success_updates_last_otp_verified_at(self, _send, _gen):
        user = self._verified_user(last_otp_verified_at=None)
        self.assertIsNone(user.last_otp_verified_at)
        self._login(user)
        verify = self.client.post(reverse("verify_login_otp"), {"otp": "123456"})
        self.assertRedirects(verify, reverse("student_dashboard"), fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertIsNotNone(user.last_otp_verified_at)
        self.assertTrue(has_recent_login_2fa_otp(self.client.session))

    @patch("accounts.views.generate_login_otp", return_value="123456")
    @patch("accounts.views.send_login_otp_email")
    def test_enabling_2fa_after_disabled_requires_otp_on_next_login(self, send_otp, _gen):
        user = self._verified_user(login_2fa_enabled=False)
        self.client.force_login(user)
        self.client.post(
            reverse("update_login_security"),
            {"login_2fa_enabled": "on", "login_2fa_mode": "interval", "login_2fa_days": "1"},
        )
        self.client.logout()
        user.refresh_from_db()
        self.assertTrue(user.login_2fa_enabled)

        response = self._login(user)
        self.assertRedirects(response, reverse("verify_login_otp"))
        send_otp.assert_called_once()


@override_settings(ROOT_URLCONF="kodehax_academy.urls")
class ProfileSecurityRenderingTests(TestCase):
    password = "CorrectHorseBattery9!"

    def setUp(self):
        self.user = User.objects.create_user(
            username="renderuser",
            email="renderuser@example.com",
            password=self.password,
            role="student",
            is_active=True,
            is_email_verified=True,
            login_2fa_enabled=True,
            login_2fa_mode="interval",
            login_2fa_days=14,
        )
        self.client.force_login(self.user)

    def test_desktop_profile_renders_security_policy(self):
        response = self.client.get(
            reverse("student_profile"), HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64)"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Two-factor authentication")
        self.assertContains(response, 'value="14"')

    @override_settings(
        MOBILE_TEMPLATE_ALLOWLIST={"user/base.html", "student/profile.html"}
    )
    def test_mobile_profile_renders_same_policy(self):
        response = self.client.get(
            reverse("student_profile"), HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Two-factor authentication")
        self.assertContains(response, 'value="14"')
