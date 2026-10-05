from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from skill_assessment.models import CodingProblem
from users.models import User

from .models import DailyChallenge, DailyChallengeSession, DailyChallengeSet, StudentPoints
from .services import (
    _normalize_test_cases,
    _render_template_value,
    _run_code,
    _should_regenerate_existing_set,
    _today,
    get_today_challenge_set,
    preview_solution,
    refresh_challenge_set,
)


class DailyChallengeWorkspaceTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student1",
            password="testpass123",
            role="student",
        )
        self.client.force_login(self.student)
        self.challenge_date = _today()

        self.problem_one = CodingProblem.objects.create(
            title="Count twos",
            topic="loops",
            description="Return the number of twos.",
            starter_code="def count_target(values):\n    return 0\n",
            function_name="count_target",
            test_cases=[{"input": [[2, 2, 1]], "expected": 2}],
            difficulty=CodingProblem.DIFFICULTY_BEGINNER,
            is_active=True,
        )
        self.problem_two = CodingProblem.objects.create(
            title="Count threes",
            topic="loops",
            description="Return the number of threes.",
            starter_code="def count_target(values):\n    return 0\n",
            function_name="count_target",
            test_cases=[{"input": [[3, 3, 1]], "expected": 2}],
            difficulty=CodingProblem.DIFFICULTY_BEGINNER,
            is_active=True,
        )
        self.challenge_set = DailyChallengeSet.objects.create(student=self.student, date=self.challenge_date)
        self.challenge_one = DailyChallenge.objects.create(
            challenge_set=self.challenge_set,
            student=self.student,
            problem=self.problem_one,
            date=self.challenge_date,
            title="Count occurrences of 2",
            description="Solve the first problem.",
            topic="loops",
            starter_code=self.problem_one.starter_code,
            function_name=self.problem_one.function_name,
            test_cases=self.problem_one.test_cases,
            difficulty=DailyChallenge.DIFFICULTY_EASY,
            level=1,
            question_number=1,
            points=5,
        )
        self.challenge_two = DailyChallenge.objects.create(
            challenge_set=self.challenge_set,
            student=self.student,
            problem=self.problem_two,
            date=self.challenge_date,
            title="Count occurrences of 3",
            description="Solve the second problem.",
            topic="loops",
            starter_code=self.problem_two.starter_code,
            function_name=self.problem_two.function_name,
            test_cases=self.problem_two.test_cases,
            difficulty=DailyChallenge.DIFFICULTY_EASY,
            level=1,
            question_number=2,
            points=5,
        )
        self.challenge_three = DailyChallenge.objects.create(
            challenge_set=self.challenge_set,
            student=self.student,
            problem=self.problem_two,
            date=self.challenge_date,
            title="Count occurrences of 3 again",
            description="Solve the last problem.",
            topic="loops",
            starter_code=self.problem_two.starter_code,
            function_name=self.problem_two.function_name,
            test_cases=self.problem_two.test_cases,
            difficulty=DailyChallenge.DIFFICULTY_EASY,
            level=1,
            question_number=3,
            points=5,
        )

    @patch("daily_challenges.services._run_code")
    def test_successful_submission_redirects_to_next_challenge_and_updates_scores(self, run_code_mock):
        run_code_mock.return_value = (
            [{"passed": True, "actual": 2, "expected": 2, "input": [[2, 2, 1]], "error_type": "", "error_category": "", "error": ""}],
            None,
            12.5,
        )

        response = self.client.post(
            reverse("daily_challenge_workspace", args=[self.challenge_one.id]),
            {"action": "submit", "code": "def count_target(values):\n    return 2"},
            follow=True,
        )

        self.challenge_one.refresh_from_db()
        self.challenge_set.refresh_from_db()
        student_points = StudentPoints.objects.get(student=self.student)
        session = DailyChallengeSession.objects.get(student=self.student, date=self.challenge_set.date)

        self.assertRedirects(response, reverse("daily_challenge_workspace", args=[self.challenge_two.id]))
        self.assertEqual(self.challenge_one.status, DailyChallenge.STATUS_SOLVED)
        self.assertEqual(self.challenge_one.score, 5)
        self.assertEqual(self.challenge_set.total_score, 5)
        self.assertEqual(student_points.total_points, 5)
        self.assertEqual(student_points.daily_points, 5)
        self.assertEqual(student_points.points_remaining, 5)
        self.assertEqual(session.points_earned, 5)
        self.assertEqual(session.points_deducted, 0)
        self.assertEqual(session.session_score, 5)
        self.assertContains(response, "Question score: +5. Daily score: 5.")
        self.assertContains(response, "Total Earned Points")
        self.assertContains(response, "Current session score:")

    def test_workspace_shows_daily_score_separately_from_hint_balance(self):
        self.challenge_one.score = 4
        self.challenge_one.status = DailyChallenge.STATUS_SOLVED
        self.challenge_one.hints_used = 1
        self.challenge_one.save(update_fields=["score", "status", "hints_used", "updated_at"])
        refresh_challenge_set(self.challenge_set)

        response = self.client.get(reverse("daily_challenge_workspace", args=[self.challenge_one.id]))

        self.assertContains(response, "Total Earned Points")
        self.assertContains(response, "Available for hints: 0")
        self.assertContains(response, ">4</p>", html=False)

    def test_workspace_remaining_challenges_counts_from_current_challenge_forward(self):
        self.challenge_one.status = DailyChallenge.STATUS_SOLVED
        self.challenge_one.score = 5
        self.challenge_two.status = DailyChallenge.STATUS_FAILED
        self.challenge_one.save(update_fields=["status", "score", "updated_at"])
        self.challenge_two.save(update_fields=["status", "updated_at"])
        refresh_challenge_set(self.challenge_set)

        response = self.client.get(reverse("daily_challenge_workspace", args=[self.challenge_three.id]))

        self.assertContains(response, "Remaining challenges:")
        self.assertContains(response, ">1</span>", html=False)

    @patch("daily_challenges.services._run_code")
    def test_failed_preview_deducts_daily_points_only(self, run_code_mock):
        run_code_mock.return_value = (
            [{"passed": False, "actual": 1, "expected": 2, "input": [[2, 2, 1]], "error_type": "", "error_category": "", "error": ""}],
            None,
            5.0,
        )

        payload = preview_solution(self.challenge_one, "def count_target(values):\n    return 1")
        student_points = StudentPoints.objects.get(student=self.student)
        session = DailyChallengeSession.objects.get(student=self.student, date=self.challenge_set.date)

        self.assertTrue(payload["allowed"])
        self.assertEqual(payload["points_deducted"], 1)
        self.assertEqual(session.points_deducted, 1)
        self.assertEqual(session.session_score, -1)
        self.assertEqual(student_points.total_points, 0)
        self.assertEqual(student_points.daily_points, -1)

    def test_expression_expected_values_are_evaluated(self):
        rendered = _render_template_value(
            "sum(1 for char in 'education' if char in 'aeiouAEIOU' and char.lower() != '{blocked}')",
            {"blocked": "o"},
        )

        self.assertEqual(rendered, 4)

    def test_legacy_expression_test_cases_are_normalized(self):
        normalized = _normalize_test_cases(
            [
                {
                    "input": [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]],
                    "expected": "[value for value in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] if value % 4 == 0]",
                },
                {
                    "input": [[4, 5, 8, 12]],
                    "expected": "[value for value in [4, 5, 8, 12] if value % 4 == 0]",
                },
            ]
        )

        self.assertEqual(normalized[0]["expected"], [4, 8])
        self.assertEqual(normalized[1]["expected"], [4, 8, 12])

    def test_run_code_allows_safe_standard_library_imports(self):
        results, error_payload, _ = _run_code(
            self.challenge_one,
            "import math\n\ndef count_target(values):\n    return math.floor(2.9)\n",
        )

        self.assertIsNone(error_payload)
        self.assertEqual(results[0]["actual"], 2)

    def test_short_source_pool_does_not_regenerate_the_same_short_set(self):
        CodingProblem.objects.exclude(
            pk__in=[self.problem_one.pk, self.problem_two.pk]
        ).update(is_active=False)
        self.assertFalse(_should_regenerate_existing_set(self.challenge_set))

    @patch("daily_challenges.services.refresh_challenge_set")
    def test_dashboard_read_can_skip_recalculation_and_reuse_prefetch(self, refresh):
        CodingProblem.objects.exclude(
            pk__in=[self.problem_one.pk, self.problem_two.pk]
        ).update(is_active=False)
        challenge_set = get_today_challenge_set(
            self.student,
            refresh_existing=False,
        )

        self.assertEqual(challenge_set.pk, self.challenge_set.pk)
        self.assertEqual(len(challenge_set.challenges.all()), 3)
        refresh.assert_not_called()
