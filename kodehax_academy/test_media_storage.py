"""Storage-selection contract and remote-storage compatibility tests.

These tests never contact a real storage provider. They only assert the
configuration contract (development vs. production), fail-closed behavior,
preserved staticfiles backend, and that file evaluation works with a storage
backend that exposes no local ``.path``.
"""
import os
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile, File
from django.core.files.storage import FileSystemStorage, storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from kodehax_academy.settings import MEDIA_STORAGE_REQUIRED_VARS, build_storages
from teacher.models import Assignment, ClassRoom, Submission
from teacher.services.evaluation import _read_text_file, grade_file_submission_ai
from users.models import User

S3_BACKEND = "storages.backends.s3.S3Storage"
LOCAL_BACKEND = "django.core.files.storage.FileSystemStorage"
STATICFILES_BACKEND = "django.contrib.staticfiles.storage.StaticFilesStorage"

DUMMY_PRODUCTION_ENV = {
    "MEDIA_STORAGE_BUCKET_NAME": "dummy-bucket",
    "MEDIA_STORAGE_ACCESS_KEY_ID": "dummy-access-key",
    "MEDIA_STORAGE_SECRET_ACCESS_KEY": "dummy-secret-key",
    "MEDIA_STORAGE_ENDPOINT_URL": "https://storage.invalid",
    "MEDIA_STORAGE_REGION_NAME": "auto",
}


class StorageSelectionTests(SimpleTestCase):
    def test_development_uses_local_filesystem_media(self):
        storages_config = build_storages(production=False)
        self.assertEqual(storages_config["default"]["BACKEND"], LOCAL_BACKEND)
        self.assertNotIn("OPTIONS", storages_config["default"])

    def test_development_preserves_staticfiles_backend(self):
        storages_config = build_storages(production=False)
        self.assertEqual(
            storages_config["staticfiles"]["BACKEND"], STATICFILES_BACKEND
        )

    def test_production_selects_durable_storage_when_configured(self):
        with patch.dict(os.environ, DUMMY_PRODUCTION_ENV, clear=False):
            storages_config = build_storages(production=True)
        self.assertEqual(storages_config["default"]["BACKEND"], S3_BACKEND)
        options = storages_config["default"]["OPTIONS"]
        self.assertEqual(options["bucket_name"], "dummy-bucket")
        self.assertEqual(options["access_key"], "dummy-access-key")
        self.assertEqual(options["secret_key"], "dummy-secret-key")
        self.assertEqual(options["endpoint_url"], "https://storage.invalid")
        self.assertEqual(options["region_name"], "auto")
        # Uploads stay private; url() must be a short-lived signed link.
        self.assertTrue(options["querystring_auth"])
        self.assertIsNone(options["default_acl"])
        self.assertFalse(options["file_overwrite"])

    def test_production_preserves_staticfiles_backend(self):
        with patch.dict(os.environ, DUMMY_PRODUCTION_ENV, clear=False):
            storages_config = build_storages(production=True)
        self.assertEqual(
            storages_config["staticfiles"]["BACKEND"], STATICFILES_BACKEND
        )

    def test_production_never_falls_back_to_ephemeral_local_media(self):
        with patch.dict(os.environ, DUMMY_PRODUCTION_ENV, clear=False):
            storages_config = build_storages(production=True)
        self.assertNotEqual(storages_config["default"]["BACKEND"], LOCAL_BACKEND)

    def test_production_endpoint_and_region_are_optional(self):
        required_only = {
            name: DUMMY_PRODUCTION_ENV[name] for name in MEDIA_STORAGE_REQUIRED_VARS
        }
        with patch.dict(os.environ, required_only, clear=False):
            with patch.dict(
                os.environ,
                {"MEDIA_STORAGE_ENDPOINT_URL": "", "MEDIA_STORAGE_REGION_NAME": ""},
            ):
                options = build_storages(production=True)["default"]["OPTIONS"]
        self.assertNotIn("endpoint_url", options)
        self.assertNotIn("region_name", options)

    def test_production_fails_closed_when_each_variable_is_missing(self):
        for missing_name in MEDIA_STORAGE_REQUIRED_VARS:
            with self.subTest(missing=missing_name):
                env = dict(DUMMY_PRODUCTION_ENV)
                env.pop(missing_name)
                with patch.dict(os.environ, env, clear=False):
                    with patch.dict(os.environ, {missing_name: ""}):
                        with self.assertRaises(ImproperlyConfigured) as ctx:
                            build_storages(production=True)
                self.assertIn(missing_name, str(ctx.exception))

    def test_error_message_names_variables_without_values(self):
        with patch.dict(
            os.environ,
            {name: "" for name in MEDIA_STORAGE_REQUIRED_VARS},
            clear=False,
        ):
            with self.assertRaises(ImproperlyConfigured) as ctx:
                build_storages(production=True)
        message = str(ctx.exception)
        for name in MEDIA_STORAGE_REQUIRED_VARS:
            self.assertIn(name, message)

    def test_active_test_settings_use_local_media_and_preserve_staticfiles(self):
        self.assertEqual(storages["default"].__class__, FileSystemStorage)
        self.assertEqual(
            self._staticfiles_backend(), STATICFILES_BACKEND
        )

    @staticmethod
    def _staticfiles_backend():
        from django.conf import settings

        return settings.STORAGES["staticfiles"]["BACKEND"]


class _NoPathStorage(FileSystemStorage):
    """In-memory storage that deliberately exposes no local filesystem path.

    Mimics remote/object storage (e.g. S3) where ``FieldFile.path`` is not
    available, so any code relying on a local path fails loudly.
    """

    def __init__(self):
        super().__init__()
        self._files = {}

    def _open(self, name, mode="rb"):
        return File(BytesIO(self._files[name]), name=name)

    def _save(self, name, content):
        content.seek(0)
        self._files[name] = content.read()
        return name

    def exists(self, name):
        return name in self._files

    def delete(self, name):
        self._files.pop(name, None)

    def url(self, name):
        return f"memory://{name}"

    def path(self, name):
        raise NotImplementedError("remote storage has no local path")


class RemoteStorageCompatibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user(username="media_teacher", role="teacher")
        cls.student = User.objects.create_user(username="media_student", role="student")
        cls.classroom = ClassRoom.objects.create(
            name="Media classroom", teacher=cls.teacher
        )
        cls.assignment = Assignment.objects.create(
            classroom=cls.classroom,
            title="Text exercise",
            description="Submit a text file.",
            due_date=timezone.now() + timedelta(days=1),
        )

    def _make_submission(self, filename=b"solution.txt", content=b"print('hello')\n"):
        field = Submission._meta.get_field("file")
        storage = _NoPathStorage()
        with patch.object(field, "storage", storage):
            submission = Submission.objects.create(
                assignment=self.assignment, student=self.student
            )
            submission.file.save(filename, ContentFile(content))
            submission.save()
            # Prove the storage backend never exposes a local path.
            with self.assertRaises(NotImplementedError):
                _ = submission.file.path
            return submission, storage, field

    def test_text_extraction_works_without_local_path(self):
        submission, _, _ = self._make_submission(
            filename="solution.py", content=b"print('hello')\n"
        )
        self.assertEqual(_read_text_file(submission.file), "print('hello')\n")

    def test_text_extraction_rejects_non_text_extensions(self):
        submission, _, _ = self._make_submission(
            filename="archive.zip", content=b"PK\x03\x04binary"
        )
        self.assertEqual(_read_text_file(submission.file), "")

    def test_text_extraction_returns_empty_for_missing_file(self):
        field = Submission._meta.get_field("file")
        storage = _NoPathStorage()
        with patch.object(field, "storage", storage):
            submission = Submission.objects.create(
                assignment=self.assignment, student=self.student
            )
            self.assertEqual(_read_text_file(submission.file), "")

    def test_ai_grading_reads_remote_storage(self):
        submission, _, _ = self._make_submission(
            filename="solution.txt", content=b"print('hello')\n"
        )
        with patch(
            "teacher.services.evaluation.generate_text", return_value="85 Nice work"
        ) as generate:
            grade_file_submission_ai(submission)
        submission.refresh_from_db()
        self.assertEqual(submission.score, 85)
        self.assertIn("Nice work", submission.ai_feedback)
        self.assertIn("print('hello')", generate.call_args.args[0])

    def test_local_storage_submission_roundtrip_still_works(self):
        upload = SimpleUploadedFile(
            "solution.txt", b"local submission", content_type="text/plain"
        )
        submission = Submission.objects.create(
            assignment=self.assignment, student=self.student, file=upload
        )
        with submission.file.open("rb") as uploaded:
            self.assertEqual(uploaded.read(), b"local submission")
