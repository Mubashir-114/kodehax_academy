"""Characterize existing journeys with the application's real URL configuration."""
import json
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.tokens import email_verification_token
from adminpanel.models import SiteSettings
from student.models import ChatSession
from teacher.models import Assignment, ClassRoom, CodeSubmission, QuizAnswer, QuizQuestion, Submission
from teacher.services.evaluation import evaluate_quiz_for_student, grade_code_submission_ai
from chat.ai_service import AIServiceError
from teacher.services.performance import get_student_performance_summary
from users.models import User


@override_settings(
    ROOT_URLCONF="kodehax_academy.urls",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    GROQ_API_KEY="",
    SECURE_SSL_REDIRECT=False,
)
class RealRouteJourneyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user(username="review_teacher", role="teacher")
        cls.student = User.objects.create_user(username="review_student", role="student")
        cls.other_student = User.objects.create_user(username="review_other", role="student")
        cls.other_teacher = User.objects.create_user(username="review_other_teacher", role="teacher")
        cls.admin = User.objects.create_user(username="review_admin", role="admin", is_staff=True)
        cls.classroom = ClassRoom.objects.create(
            name="Review classroom", teacher=cls.teacher, readme_content="# Course README"
        )
        cls.classroom.students.add(cls.student)
        cls.assignment = Assignment.objects.create(
            classroom=cls.classroom, title="File exercise", description="Submit a text file.",
            due_date=timezone.now() + timedelta(days=3),
        )

    def setUp(self):
        # SiteSettings caches model instances across transactions; isolate each test.
        cache.clear()
        self.addCleanup(cache.clear)

    def test_registration_and_verification_keep_account_inactive_until_verified(self):
        with patch("accounts.views.send_verification_email") as send_email:
            response = self.client.post(reverse("register"), {
                "username": "review_new_student", "email": "review_new@example.com",
                "password1": "ReviewPassword!3491", "password2": "ReviewPassword!3491",
            })
        self.assertRedirects(response, reverse("registration_success"), fetch_redirect_response=False)
        user = User.objects.get(username="review_new_student")
        self.assertEqual(user.role, "student")
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)
        send_email.assert_called_once()
        url = reverse("verify_email", kwargs={
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": email_verification_token.make_token(user),
        })
        self.assertRedirects(self.client.get(url), reverse("student_login"), fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_email_verified)

    def test_anonymous_redirects_preserve_portal_login_destinations(self):
        for route, destination in (("student_dashboard", "student_login"),
                                   ("teacher_dashboard", "teacher_login")):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, reverse(destination) + "?next=" + reverse(route))
        self.assertRedirects(self.client.get(reverse("adminpanel_dashboard")),
                             reverse("home"), fetch_redirect_response=False)

    def test_cross_role_portal_access_is_denied(self):
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get(reverse("teacher_dashboard")),
                             reverse("home"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("adminpanel_dashboard")),
                             reverse("student_dashboard"), fetch_redirect_response=False)
        self.client.force_login(self.teacher)
        self.assertRedirects(self.client.get(reverse("student_dashboard")),
                             reverse("home"), fetch_redirect_response=False)

    def test_classroom_creation_and_code_enrollment(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("create_class"), {
            "name": "New review classroom", "description": "Basics", "readme_content": "# Welcome",
        })
        self.assertRedirects(response, reverse("teacher_dashboard"), fetch_redirect_response=False)
        classroom = ClassRoom.objects.get(name="New review classroom")
        self.assertEqual(classroom.teacher, self.teacher)
        self.client.force_login(self.other_student)
        response = self.client.post(reverse("join_classroom"), {"class_code": classroom.class_code.lower()})
        self.assertRedirects(response, reverse("student_dashboard"), fetch_redirect_response=False)
        self.assertTrue(classroom.students.filter(pk=self.other_student.pk).exists())
        self.assertEqual(self.client.session["student_active_classroom_id"], classroom.pk)

    def test_classroom_and_assignment_ownership_boundaries(self):
        self.client.force_login(self.other_teacher)
        response = self.client.get(reverse("class_detail", args=[self.classroom.pk]))
        self.assertRedirects(response, reverse("teacher_dashboard"), fetch_redirect_response=False)
        self.client.force_login(self.other_student)
        self.assertEqual(self.client.get(reverse("student_class_detail", args=[self.classroom.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("submit_assignment", args=[self.assignment.pk])).status_code, 404)

    def test_file_assignment_creation_and_submission_roundtrip(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("create_file_assignment", args=[self.classroom.pk]), {
            "title": "New file exercise", "description": "Attach a text file",
            "due_date": (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
            "attempt_policy": Assignment.ATTEMPT_POLICY_ONCE,
        })
        self.assertRedirects(response, reverse("assignment_list", args=[self.classroom.pk]),
                             fetch_redirect_response=False)
        assignment = Assignment.objects.get(title="New file exercise")
        self.client.force_login(self.student)
        with tempfile.TemporaryDirectory(prefix="kodehax-review-media-") as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(reverse("submit_assignment", args=[assignment.pk]), {
                    "file": SimpleUploadedFile("solution.txt", b"review submission", content_type="text/plain"),
                })
                self.assertEqual(response.status_code, 302)
                submission = Submission.objects.get(assignment=assignment, student=self.student)
                with submission.file.open("rb") as uploaded:
                    self.assertEqual(uploaded.read(), b"review submission")

    def test_quiz_scoring_and_performance_snapshot(self):
        quiz = Assignment.objects.create(
            classroom=self.classroom, title="Two-question quiz", description="Quiz", assignment_type="quiz",
            due_date=timezone.now() + timedelta(days=3), max_score=100,
        )
        for answer, selected in (("A", "A"), ("B", "C")):
            question = QuizQuestion.objects.create(assignment=quiz, question="Choose", option_a="1",
                                                   option_b="2", option_c="3", option_d="4", correct_answer=answer)
            QuizAnswer.objects.create(question=question, student=self.student, selected_option=selected)
        result = evaluate_quiz_for_student(quiz, self.student)
        self.assertEqual(result.score, 50)
        self.assertEqual(result.correct_answers, 1)
        self.assertEqual(result.feedback, "Auto-graded quiz: 1/2 correct.")
        summary = get_student_performance_summary(self.student)["summary"]
        self.assertEqual(summary["average_score"], 50)
        self.assertEqual(summary["assignments_completed"], 1)
        self.assertEqual(summary["total_assignments"], 2)

    def test_existing_all_a_quiz_compatibility_rule_is_retained(self):
        quiz = Assignment.objects.create(classroom=self.classroom, title="Legacy quiz", description="Quiz",
                                         assignment_type="quiz", due_date=timezone.now() + timedelta(days=3))
        question = QuizQuestion.objects.create(assignment=quiz, question="Choose", option_a="1", option_b="2",
                                               option_c="3", option_d="4", correct_answer="A")
        QuizAnswer.objects.create(question=question, student=self.student, selected_option="D")
        result = evaluate_quiz_for_student(quiz, self.student)
        self.assertEqual(result.score, 100)

    def test_chat_methods_payloads_and_session_ownership(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("api_chat_start")).status_code, 405)
        response = self.client.post(reverse("api_chat_start"), json.dumps({"message": "Learning loops"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json()), {"session", "memory"})
        session_id = response.json()["session"]["id"]
        detail_url = reverse("api_chat_session_detail", args=[session_id])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"session", "messages", "memory"})
        self.assertEqual(response.json()["messages"][0]["content"], "Learning loops")
        self.client.force_login(self.other_student)
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "Session not found."})
        self.client.force_login(self.student)
        self.assertEqual(self.client.delete(detail_url).json(), {"success": True})
        self.assertFalse(ChatSession.objects.get(pk=session_id).is_active)

    def test_text_chat_validates_json_before_requesting_ai(self):
        self.client.force_login(self.student)
        with patch("student.views.generate_text") as generate:
            response = self.client.post(reverse("ai_chat"), "{", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid JSON"})
        generate.assert_not_called()

    def test_maintenance_health_and_non_superuser_redirect(self):
        state = SiteSettings.load()
        state.maintenance_mode = True
        state.save()
        response = self.client.get(reverse("health_check"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})
        self.assertRedirects(self.client.get(reverse("home")), reverse("maintenance_page"),
                             fetch_redirect_response=False)
        response = self.client.get(reverse("maintenance_page"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "600")

    def test_home_uses_existing_desktop_and_mobile_templates(self):
        desktop = self.client.get(reverse("home"), HTTP_USER_AGENT="Desktop")
        mobile = self.client.get(reverse("home"), HTTP_USER_AGENT="iPhone Mobile")
        self.assertEqual(desktop.status_code, 200)
        self.assertEqual(mobile.status_code, 200)
        self.assertTemplateUsed(desktop, "user/base.html")
        self.assertTemplateUsed(mobile, "mobile/home.html")

    def test_logout_clears_the_authenticated_session(self):
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get(reverse("logout")), reverse("home"),
                             fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


    def test_role_admin_can_render_the_real_admin_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("adminpanel_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "adminpanel/dashboard.html")

    def test_skill_assessment_first_step_and_weighted_scoring(self):
        from skill_assessment.models import StudentAssessment, StudentSkill
        from skill_assessment.services import calculate_final_skill_score, classify_skill_level

        self.client.force_login(self.student)
        response = self.client.get(reverse("skill_assessment_entry"))
        self.assertRedirects(response, reverse("skill_assessment_step", args=[1]), fetch_redirect_response=False)
        response = self.client.post(reverse("skill_assessment_step", args=[1]), {
            "programming_language_familiarity": "beginner", "coding_experience_duration": "new",
            "platforms_used": [], "confidence_rating": "1",
        })
        self.assertRedirects(response, reverse("skill_assessment_step", args=[2]), fetch_redirect_response=False)
        assessment = StudentAssessment.objects.get(student=self.student)
        self.assertEqual(assessment.self_assessment_score, 19)
        self.assertEqual(assessment.current_step, 2)
        self.assertEqual(calculate_final_skill_score(20, 50, 80), 59)
        self.assertEqual(classify_skill_level(59), StudentSkill.LEVEL_INTERMEDIATE)

    def test_ai_chat_response_uses_existing_model_and_json_contract(self):
        self.client.force_login(self.student)
        with patch("student.views.generate_text", return_value=json.dumps({
            "type": "explanation", "title": "Loops", "content": "A loop repeats an action.",
            "examples": [], "quiz": [], "follow_up": [], "difficulty": "easy", "tags": ["loops"],
        })) as generate:
            response = self.client.post(reverse("ai_chat"), json.dumps({"message": "Explain loops"}),
                                        content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"reply", "has_code", "structured", "context"})
        self.assertIn("A loop repeats an action.", response.json()["reply"])
        self.assertIn("Explain loops", generate.call_args.args[0])
        self.assertEqual(set(generate.call_args.kwargs["schema"]), {"type", "title", "content", "examples", "quiz", "follow_up", "difficulty", "tags"})

    @override_settings(GROQ_API_KEY="review-only-placeholder")
    def test_teacher_notes_generation_renders_with_mocked_ai(self):
        self.client.force_login(self.teacher)
        with patch("teacher.services.ai_tools.generate_text", return_value="# Loop notes\nRepeat actions.") as generate:
            response = self.client.post(reverse("ai_tools"), {"tool": "notes", "notes_topic": "Loops"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "teacher/ai_tools.html")
        self.assertEqual(response.context["result"], "# Loop notes\nRepeat actions.")
        self.assertIn("Loops", generate.call_args.args[0])

    def test_groq_rubric_preserves_score_scaling_and_snapshot(self):
        submission = CodeSubmission.objects.create(assignment=self.assignment, student=self.student,
                                                   language="python", code="print(1)")
        rubric = {"syntax": 10, "logic": 8, "structure": 6, "readability": 8, "summary": "Synthetic feedback"}
        with patch("teacher.services.evaluation.generate_text", return_value=json.dumps(rubric)) as generate:
            grade_code_submission_ai(submission)
        submission.refresh_from_db()
        self.assertEqual(submission.score, 80)
        self.assertIn("Logic: 8.0/10", submission.ai_feedback)
        self.assertEqual(set(generate.call_args.kwargs["schema"]), set(rubric))
        self.assertEqual(get_student_performance_summary(self.student)["summary"]["average_score"], 80)

    def test_groq_rubric_retains_python_syntax_override(self):
        submission = CodeSubmission.objects.create(assignment=self.assignment, student=self.student,
                                                   language="python", code="if:")
        rubric = {"syntax": 10, "logic": 10, "structure": 10, "readability": 10, "summary": "Synthetic"}
        with patch("teacher.services.evaluation.generate_text", return_value=json.dumps(rubric)):
            grade_code_submission_ai(submission)
        self.assertEqual(submission.score, 75)
        self.assertIn("Syntax: 0.0/10", submission.ai_feedback)

    def test_malformed_groq_rubric_uses_existing_safe_failure_score(self):
        submission = CodeSubmission.objects.create(assignment=self.assignment, student=self.student,
                                                   language="python", code="print(1)")
        error = AIServiceError("malformed_output", "Invalid provider output", "Invalid JSON", "Retry")
        with patch("teacher.services.evaluation.generate_text", side_effect=error) as generate:
            grade_code_submission_ai(submission)
        self.assertEqual(submission.score, 0)
        self.assertIn("AI service is temporarily unavailable", submission.ai_feedback)
        self.assertEqual(generate.call_count, 1)

    def test_groq_chat_quota_retains_route_status_and_payload(self):
        self.client.force_login(self.student)
        error = AIServiceError("quota", "AI limit reached", "Synthetic quota message", "Retry", 429)
        with patch("student.views.generate_text", side_effect=error):
            response = self.client.post(reverse("ai_chat"), json.dumps({"message": "Explain loops"}),
                                        content_type="application/json")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(set(response.json()), {"error", "ai_error"})
        self.assertEqual(response.json()["ai_error"]["code"], "service_busy")

    def test_image_route_preserves_response_schema(self):
        from io import BytesIO
        from PIL import Image
        self.client.force_login(self.student)
        buffer = BytesIO()
        Image.new("RGB", (10, 10)).save(buffer, format="PNG")
        payload = {"type": "math", "detected_content": "2+2", "explanation": "Add.", "steps": [],
                   "solution": "4", "mistakes": [], "follow_up": ["Practice"]}
        with tempfile.TemporaryDirectory(prefix="kodehax-vision-media-") as media_root:
            with override_settings(MEDIA_ROOT=media_root), patch("student.views.upload_image_to_ai", return_value=payload):
                response = self.client.post(reverse("api_image_query"), {
                    "image": SimpleUploadedFile("synthetic.png", buffer.getvalue(), content_type="image/png"),
                })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json()), {"reply", "has_code", "structured", "session", "image_query"})
        self.assertEqual(response.json()["image_query"]["raw"], payload)
