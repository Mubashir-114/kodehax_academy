"""Tests for the ``ensure_admin`` management command.

These tests use the repository's SQLite test settings only (no production
database) and never perform real network calls. Interactive input and the
password prompt are mocked.
"""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase, override_settings

User = get_user_model()

VALID_PASSWORD = "Kx7!Vt2#Qm"
GETPASS = "users.management.commands.ensure_admin.getpass.getpass"


def run_command(inputs, passwords, **options):
    """Run the command with mocked interactive input; return (stdout, stderr)."""
    out, err = StringIO(), StringIO()
    with patch("builtins.input", side_effect=inputs):
        with patch(GETPASS, side_effect=passwords):
            call_command("ensure_admin", stdout=out, stderr=err, **options)
    return out.getvalue(), err.getvalue()


class EnsureAdminCreationTests(TestCase):
    def test_creates_admin_with_required_flags(self):
        run_command(["newadmin", "newadmin@example.com"], [VALID_PASSWORD, VALID_PASSWORD])
        user = User.objects.get(username="newadmin")
        self.assertEqual(user.role, "admin")
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.email, "newadmin@example.com")

    def test_creates_admin_password_is_hashed(self):
        run_command(["newadmin", "newadmin@example.com"], [VALID_PASSWORD, VALID_PASSWORD])
        user = User.objects.get(username="newadmin")
        self.assertNotEqual(user.password, VALID_PASSWORD)
        self.assertTrue(user.password.startswith(("pbkdf2_", "argon2")))
        self.assertTrue(user.check_password(VALID_PASSWORD))

    def test_password_validation_enforced(self):
        with self.assertRaises(CommandError) as ctx:
            run_command(["newadmin", "newadmin@example.com"], ["short", "short"])
        self.assertIn("rejected", str(ctx.exception).lower())
        self.assertFalse(User.objects.filter(username="newadmin").exists())

    def test_confirmation_mismatch_rejected(self):
        with self.assertRaises(CommandError) as ctx:
            run_command(["newadmin", "newadmin@example.com"], [VALID_PASSWORD, "Different!9Xy"])
        self.assertIn("did not match", str(ctx.exception).lower())
        self.assertFalse(User.objects.filter(username="newadmin").exists())

    def test_username_prefilled_by_option(self):
        run_command([], [VALID_PASSWORD, VALID_PASSWORD], username="optadmin", email="opt@example.com")
        self.assertTrue(User.objects.filter(username="optadmin", role="admin").exists())

    def test_never_outputs_password(self):
        out, err = run_command(
            ["newadmin", "newadmin@example.com"], [VALID_PASSWORD, VALID_PASSWORD]
        )
        combined = out + err
        self.assertNotIn(VALID_PASSWORD, combined)
        self.assertNotIn("password=", combined)

    def test_failed_creation_rolls_back(self):
        with patch.object(User, "save", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                run_command(
                    ["newadmin", "newadmin@example.com"],
                    [VALID_PASSWORD, VALID_PASSWORD],
                )
        self.assertFalse(User.objects.filter(username="newadmin").exists())

    def test_blank_username_rejected(self):
        with self.assertRaises(CommandError):
            run_command(["", "newadmin@example.com"], [VALID_PASSWORD, VALID_PASSWORD])


class EnsureAdminExistingUserTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="stu", email="stu@example.com", password="Stu-Pass!9", role="student"
        )
        self.teacher = User.objects.create_user(
            username="tea", email="tea@example.com", password="Tea-Pass!9", role="teacher"
        )

    def test_existing_student_not_promoted_without_flag(self):
        with self.assertRaises(CommandError) as ctx:
            run_command(["stu"], [])
        self.assertIn("promote-existing", str(ctx.exception))
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, "student")
        self.assertFalse(self.student.is_staff)
        self.assertFalse(self.student.is_superuser)

    def test_existing_student_promoted_with_flag_and_confirmation(self):
        out, _ = run_command(
            ["stu", "y"], [VALID_PASSWORD, VALID_PASSWORD], promote_existing=True
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, "admin")
        self.assertTrue(self.student.is_active)
        self.assertTrue(self.student.is_staff)
        self.assertTrue(self.student.is_superuser)
        self.assertTrue(self.student.check_password(VALID_PASSWORD))

    def test_existing_student_promotion_declined_changes_nothing(self):
        original_hash = self.student.password
        run_command(["stu", "n"], [], promote_existing=True)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, "student")
        self.assertEqual(self.student.password, original_hash)
        self.assertFalse(self.student.is_staff)

    def test_existing_teacher_not_promoted_without_flag(self):
        with self.assertRaises(CommandError):
            run_command(["tea"], [])
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.role, "teacher")
        self.assertFalse(self.teacher.is_superuser)


class EnsureAdminIdempotencyTests(TestCase):
    def test_existing_superuser_not_modified_when_declining(self):
        superuser = User.objects.create_superuser(
            username="root", email="root@example.com", password="Root-Pass!9"
        )
        superuser.role = "admin"
        superuser.save(update_fields=["role"])
        original_hash = superuser.password

        out, _ = run_command(["n"], [])
        self.assertIn("already exist", out)
        superuser.refresh_from_db()
        self.assertEqual(superuser.password, original_hash)
        self.assertEqual(superuser.role, "admin")
        self.assertTrue(superuser.is_superuser)

    def test_cannot_create_second_admin_without_confirmation(self):
        User.objects.create_superuser(
            username="root", email="root@example.com", password="Root-Pass!9"
        )
        run_command(["n"], [])
        self.assertEqual(User.objects.filter(username="newadmin").exists(), False)

    def test_second_admin_created_after_confirmation(self):
        User.objects.create_superuser(
            username="root", email="root@example.com", password="Root-Pass!9"
        )
        run_command(
            ["y", "newadmin", "newadmin@example.com"],
            [VALID_PASSWORD, VALID_PASSWORD],
        )
        self.assertTrue(User.objects.get(username="newadmin").is_superuser)


class EnsureAdminRoutingTests(TestCase):
    """Prove the created account satisfies the real access requirements.

    Uses the production URLconf but the SQLite test database.
    """

    @override_settings(ROOT_URLCONF="kodehax_academy.urls")
    def test_created_admin_can_reach_django_admin(self):
        run_command(["newadmin", "newadmin@example.com"], [VALID_PASSWORD, VALID_PASSWORD])
        admin = User.objects.get(username="newadmin")
        self.client.force_login(admin)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)

    @override_settings(ROOT_URLCONF="kodehax_academy.urls")
    def test_created_admin_can_reach_admin_panel(self):
        run_command(["newadmin", "newadmin@example.com"], [VALID_PASSWORD, VALID_PASSWORD])
        admin = User.objects.get(username="newadmin")
        self.client.force_login(admin)
        response = self.client.get("/admin-panel/dashboard/")
        self.assertEqual(response.status_code, 200)

    @override_settings(ROOT_URLCONF="kodehax_academy.urls")
    def test_teacher_login_page_loads(self):
        response = self.client.get("/teacher/login/")
        self.assertEqual(response.status_code, 200)

    @override_settings(ROOT_URLCONF="kodehax_academy.urls")
    def test_django_admin_requires_staff(self):
        student = User.objects.create_user(
            username="stu2", password="Stu-Pass!9", role="student"
        )
        self.client.force_login(student)
        response = self.client.get("/admin/")
        self.assertIn(response.status_code, (302, 403))


class EnsureAdminIsolationTests(TestCase):
    def test_no_production_database_contacted(self):
        # The test settings must resolve to the bundled SQLite test database.
        self.assertEqual(connection.vendor, "sqlite")
