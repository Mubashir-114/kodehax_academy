"""Interactively create or promote a single administrator account.

This command exists because the deployed database may legitimately contain no
`is_staff`/`is_superuser`/``role='admin'`` account (for example after a fresh
staging reset), which makes Django Admin unreachable. It lets an authorized
operator establish exactly one known administrator from a trusted shell.

Safety properties:
* Interactive only. Credentials are never read from the environment, settings,
  fixtures, or Git, and no default password exists.
* The plaintext password is supplied at run time, validated with Django's
  password validators, hashed with ``set_password`` and never printed or logged.
* Existing accounts are never silently promoted; ``--promote-existing`` plus an
  explicit interactive confirmation are required.
* At least one administrator is never modified without confirmation, and the
  database change is wrapped in ``transaction.atomic()``.
"""

import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

User = get_user_model()

ADMIN_ROLE = "admin"


class Command(BaseCommand):
    help = (
        "Interactively create (or, with --promote-existing, promote) a single "
        "administrator account with role='admin', is_active/is_staff/is_superuser=True. "
        "The password is supplied at run time only and is never stored in plaintext."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="",
            help="Pre-fill the username instead of prompting for it.",
        )
        parser.add_argument(
            "--email",
            default="",
            help="Pre-fill the email instead of prompting for it.",
        )
        parser.add_argument(
            "--promote-existing",
            action="store_true",
            help=(
                "Allow promoting an already-existing account to administrator. "
                "Without this flag the command refuses to touch an existing user."
            ),
        )

    # -- interaction helpers ------------------------------------------------

    def _prompt(self, label):
        try:
            return input(f"{label}: ").strip()
        except EOFError as exc:  # pragma: no cover - defensive
            raise CommandError(
                "Interactive input is required but stdin is closed."
            ) from exc

    def _prompt_password(self, label):
        try:
            return getpass.getpass(f"{label}: ")
        except EOFError as exc:  # pragma: no cover - defensive
            raise CommandError(
                "Interactive input is required but stdin is closed."
            ) from exc

    def _confirm(self, question, default=False):
        suffix = " [Y/n]: " if default else " [y/N]: "
        try:
            answer = input(f"{question}{suffix}").strip().lower()
        except EOFError as exc:  # pragma: no cover - defensive
            raise CommandError(
                "Interactive input is required but stdin is closed."
            ) from exc
        if not answer:
            return default
        return answer in ("y", "yes")

    # -- reporting helpers --------------------------------------------------

    def _administrator_queryset(self):
        return (
            User.objects.filter(Q(role=ADMIN_ROLE) | Q(is_staff=True) | Q(is_superuser=True))
            .distinct()
            .order_by("pk")
        )

    def _write_existing_administrators(self, queryset):
        self.stdout.write(
            "The following administrator account(s) already exist "
            "(no password values are shown):"
        )
        for account in queryset.values(
            "pk", "username", "is_active", "is_staff", "is_superuser", "role"
        ):
            self.stdout.write(
                "  id={pk} username={username} is_active={is_active} "
                "is_staff={is_staff} is_superuser={is_superuser} role={role}".format(
                    **account
                )
            )

    def _read_password(self, user_for_validation):
        password = self._prompt_password("Password")
        confirmation = self._prompt_password("Password (again)")
        if password != confirmation:
            raise CommandError("Passwords did not match. No changes were made.")
        try:
            validate_password(password, user=user_for_validation)
        except ValidationError as exc:
            raise CommandError(
                "Password rejected: " + " ".join(exc.messages) + " No changes were made."
            )
        return password

    # -- main ---------------------------------------------------------------

    def handle(self, *args, **options):
        promote_existing = options["promote_existing"]

        existing_administrators = self._administrator_queryset()
        if existing_administrators.exists():
            self.stdout.write(
                self.style.WARNING("One or more administrator accounts already exist.")
            )
            self._write_existing_administrators(existing_administrators)
            if not self._confirm(
                "Create or promote another administrator anyway?", default=False
            ):
                self.stdout.write("No changes were made.")
                return

        username = (options["username"] or self._prompt("Username")).strip()
        if not username:
            raise CommandError("A username is required. No changes were made.")

        email_option = (options["email"] or "").strip()

        existing_user = (
            User.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=username)
            )
            .order_by("pk")
            .first()
        )

        if existing_user is not None:
            self._handle_existing_user(existing_user, promote_existing)
            return

        self._create_administrator(username, email_option)

    def _handle_existing_user(self, user, promote_existing):
        self.stdout.write("An account matching that username/email already exists:")
        for field in ("pk", "username", "is_active", "is_staff", "is_superuser", "role"):
            self.stdout.write(f"  {field}={getattr(user, field)}")

        if not promote_existing:
            raise CommandError(
                f"User '{user.username}' already exists. Refusing to modify it. "
                "Re-run with --promote-existing to promote it deliberately. "
                "No changes were made."
            )

        already_admin = bool(user.role == ADMIN_ROLE) and user.is_staff and user.is_superuser
        prompt = (
            f"Reset the password and reassert administrator access for '{user.username}'?"
            if already_admin
            else f"Promote '{user.username}' to administrator?"
        )
        if not self._confirm(prompt, default=False):
            self.stdout.write("No changes were made.")
            return

        password = self._read_password(user)

        with transaction.atomic():
            user.role = ADMIN_ROLE
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()

        self._report_success(user, promoted=True)

    def _create_administrator(self, username, email_option):
        if User.objects.filter(username__iexact=username).exists():
            # Guards against a race between the earlier lookup and here.
            raise CommandError("That username was taken while running. No changes were made.")

        email = (email_option or self._prompt("Email")).strip()
        if not email:
            raise CommandError("An email is required. No changes were made.")

        candidate = User(username=username, email=email, role=ADMIN_ROLE)
        password = self._read_password(candidate)

        with transaction.atomic():
            user = User(
                username=username,
                email=email,
                role=ADMIN_ROLE,
                is_active=True,
                is_staff=True,
                is_superuser=True,
            )
            user.set_password(password)
            user.save()

        self._report_success(user, promoted=False)

    def _report_success(self, user, promoted):
        action = "promoted to administrator" if promoted else "created as administrator"
        self.stdout.write(
            self.style.SUCCESS(
                f"Account '{user.username}' (id={user.pk}) {action}: "
                f"role={user.role}, is_active={user.is_active}, "
                f"is_staff={user.is_staff}, is_superuser={user.is_superuser}."
            )
        )
        self.stdout.write("The password was set interactively and is not displayed.")
