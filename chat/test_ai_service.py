"""Provider boundary tests use mocks; they do not establish live model access."""
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image

from chat import ai_service
from chat.schemas import CHAT_SCHEMA, RUBRIC_SCHEMA, VISION_SCHEMA, validate_json
from student.services.vision import ImageQueryError, upload_image_to_ai
from teacher.services.ai_tools import generate_quiz, generate_notes, generate_coding_assignment


CHAT = {"type": "explanation", "title": "Loops", "content": "Repeat actions.",
        "examples": [], "quiz": [], "follow_up": [], "difficulty": "easy", "tags": []}
VISION = {"type": "math", "detected_content": "2+2", "explanation": "Add two and two.",
          "steps": ["Count four"], "solution": "4", "mistakes": [], "follow_up": []}


@override_settings(GROQ_API_KEY="synthetic-key", GROQ_TEXT_MODEL="openai/gpt-oss-20b",
                   GROQ_VISION_MODEL="qwen/qwen3.8-27b")
class ProviderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = MagicMock()
        self.client.__enter__.return_value = self.client
        self.response("hello")
        self.client_patcher = patch("chat.ai_service.get_groq_client", return_value=self.client)
        self.mock_client = self.client_patcher.start()
        self.addCleanup(self.client_patcher.stop)

    def response(self, content, finish="stop"):
        self.client.chat.completions.create.return_value = SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)
        ])

    def test_text_uses_configured_model_and_user_prompt(self):
        self.assertEqual(ai_service.generate_text("Explain loops"), "hello")
        kwargs = self.client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "openai/gpt-oss-20b")
        self.assertEqual(kwargs["messages"], [{"role": "user", "content": "Explain loops"}])
        self.assertNotIn("response_format", kwargs)

    @override_settings(GROQ_TEXT_MODEL="explicit-account-model")
    def test_model_override_is_used_without_substitution(self):
        ai_service.generate_text("hello")
        self.assertEqual(self.client.chat.completions.create.call_args.kwargs["model"], "explicit-account-model")

    def test_json_contract_accepts_valid_chat(self):
        self.response(json.dumps(CHAT))
        self.assertEqual(json.loads(ai_service.generate_text("Return JSON", schema=CHAT_SCHEMA)), CHAT)
        self.assertEqual(self.client.chat.completions.create.call_args.kwargs["response_format"], {"type": "json_object"})

    def test_malformed_json_is_safe_and_recorded(self):
        self.response("not JSON; synthetic secret")
        with self.assertRaises(ai_service.AIServiceError) as caught:
            ai_service.generate_text("Return JSON", schema=CHAT_SCHEMA)
        self.assertEqual(caught.exception.code, "malformed_output")
        self.assertNotIn("synthetic secret", str(caught.exception))
        self.assertEqual(cache.get(ai_service.AI_ISSUE_CACHE_KEY)["code"], "malformed_output")

    def test_wrong_field_types_are_rejected(self):
        for bad in ({**CHAT, "content": []}, {**CHAT, "examples": [5]},
                    {**CHAT, "quiz": [{"question": "Incomplete"}]}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_json(json.dumps(bad), CHAT_SCHEMA)

    def test_json_arrays_and_empty_objects_are_rejected(self):
        for text in ("[]", "{}", "null"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_json(text)

    def test_nonfinite_or_boolean_rubric_scores_are_rejected(self):
        rubric = {"syntax": 10, "logic": 8, "structure": 7, "readability": 9, "summary": "Good"}
        for value in (float("nan"), float("inf"), True, "9"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_json(json.dumps({**rubric, "syntax": value}), RUBRIC_SCHEMA)

    def test_truncated_response_is_rejected(self):
        self.response(json.dumps(CHAT), "length")
        with self.assertRaises(ai_service.AIServiceError) as caught:
            ai_service.generate_text("Return JSON", schema=CHAT_SCHEMA)
        self.assertEqual(caught.exception.code, "malformed_output")

    def test_empty_response_is_rejected(self):
        self.response("")
        with self.assertRaises(ai_service.AIServiceError):
            ai_service.generate_text("hello")

    def test_http_failures_are_normalized_without_provider_details(self):
        for status, code, response_status in ((401, "auth", 503), (403, "auth", 503),
                                              (429, "quota", 429), (400, "invalid_request", 503),
                                              (503, "unavailable", 503)):
            exc = RuntimeError("synthetic sensitive provider detail")
            exc.status_code = status
            self.client.chat.completions.create.side_effect = exc
            with self.subTest(status=status), self.assertRaises(ai_service.AIServiceError) as caught:
                ai_service.generate_text("hello")
            self.assertEqual((caught.exception.code, caught.exception.status_code), (code, response_status))
            self.assertNotIn("sensitive", str(caught.exception))
            self.assertEqual(self.client.chat.completions.create.call_count, 1)
            self.client.chat.completions.create.reset_mock()

    def test_timeout_is_safe(self):
        self.client.chat.completions.create.side_effect = TimeoutError("sensitive details")
        with self.assertRaises(ai_service.AIServiceError) as caught:
            ai_service.generate_text("hello")
        self.assertEqual(caught.exception.code, "unavailable")

    def test_success_clears_prior_issue(self):
        cache.set(ai_service.AI_ISSUE_CACHE_KEY, {"code": "quota"})
        ai_service.generate_text("hello")
        self.assertIsNone(cache.get(ai_service.AI_ISSUE_CACHE_KEY))

    @override_settings(GROQ_API_KEY="")
    def test_missing_key_and_admin_status(self):
        self.client_patcher.stop()
        with patch("chat.ai_service.Groq") as constructor:
            with self.assertRaises(ai_service.AIServiceError) as caught:
                ai_service.get_groq_client()
        self.assertEqual(caught.exception.code, "missing_key")
        constructor.assert_not_called()
        self.assertEqual(ai_service.get_ai_service_status()["code"], "missing_key")

    def test_client_timeout_and_retries_are_bounded(self):
        self.client_patcher.stop()
        with patch("chat.ai_service.Groq") as constructor:
            ai_service.get_groq_client()
        self.assertEqual(constructor.call_args.kwargs["timeout"], 30.0)
        self.assertEqual(constructor.call_args.kwargs["max_retries"], 0)

    def test_public_error_payload_hides_admin_auth_details(self):
        exc = RuntimeError("provider key rejected")
        exc.status_code = 401
        public = ai_service.ai_error_payload(exc)
        self.assertEqual(set(public), {"code", "title", "message", "suggestion"})
        self.assertEqual(public["code"], "service_unavailable")
        self.assertNotIn("GROQ_API_KEY", json.dumps(public))
        self.assertEqual(ai_service.ai_admin_error_payload(exc)["code"], "auth")

    def test_vision_sends_reencoded_data_url_and_exact_model(self):
        self.response(json.dumps(VISION))
        image = Image.new("RGB", (10, 10), "white")
        self.addCleanup(image.close)
        ai_service.generate_image("Return JSON", image, schema=VISION_SCHEMA)
        kwargs = self.client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "qwen/qwen3.8-27b")
        self.assertEqual(kwargs["reasoning_effort"], "none")
        self.assertTrue(kwargs["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_uploaded_image_response_and_stream_position(self):
        self.response(json.dumps(VISION))
        buffer = BytesIO()
        Image.new("RGB", (10, 10), "white").save(buffer, format="PNG")
        upload = SimpleUploadedFile("synthetic.png", buffer.getvalue(), content_type="image/png")
        result = upload_image_to_ai(upload)
        self.assertEqual(result["solution"], "4")
        self.assertEqual(upload.tell(), 0)

    def test_invalid_image_does_not_call_provider(self):
        with self.assertRaises(ImageQueryError):
            upload_image_to_ai(SimpleUploadedFile("bad.png", b"not an image"))
        self.client.chat.completions.create.assert_not_called()

    def test_vision_400_does_not_retry_or_switch_models(self):
        exc = RuntimeError("private provider response")
        exc.status_code = 400
        self.client.chat.completions.create.side_effect = exc
        buffer = BytesIO()
        Image.new("RGB", (10, 10)).save(buffer, format="PNG")
        with self.assertRaises(ImageQueryError) as caught:
            upload_image_to_ai(SimpleUploadedFile("synthetic.png", buffer.getvalue()))
        self.assertNotIn("private", str(caught.exception))
        self.assertEqual(self.client.chat.completions.create.call_count, 1)

    def test_teacher_studio_uses_shared_provider(self):
        with patch("teacher.services.ai_tools.generate_text", return_value="Synthetic content") as generate:
            self.assertEqual(generate_notes("Loops"), "Synthetic content")
            self.assertEqual(generate_coding_assignment("Loops"), "Synthetic content")
        self.assertEqual(generate.call_count, 2)

    def test_quiz_count_correction_preserves_requested_count(self):
        with patch("teacher.services.ai_tools.generate_text", side_effect=["Q1. One", "Q1. One\nQ2. Two"]) as generate:
            result = generate_quiz("2 questions")
        self.assertEqual(result, "Q1. One\nQ2. Two")
        self.assertEqual(generate.call_count, 2)
        self.assertIn("exactly 2", generate.call_args.args[0])
