from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from daily_challenges.models import (
    DailyChallenge,
    DailyChallengeSession,
    DailyChallengeSet,
    StudentPoints,
)
from daily_challenges.services import _today
from skill_assessment.models import CodingProblem, StudentSkill
from teacher.models import Assignment, ClassRoom
from users.models import User

from .models import StudentProfile


class StudentDashboardPerformanceTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="dashboard-student",
            password="testpass123",
            role="student",
            is_email_verified=True,
        )
        self.teacher = User.objects.create_user(
            username="dashboard-teacher",
            password="testpass123",
            role="teacher",
            is_email_verified=True,
        )
        StudentSkill.objects.create(
            student=self.student,
            skill_score=50,
            skill_level=StudentSkill.LEVEL_INTERMEDIATE,
        )
        StudentProfile.objects.create(user=self.student)
        classroom = ClassRoom.objects.create(
            name="Measured Classroom",
            teacher=self.teacher,
        )
        classroom.students.add(self.student)
        Assignment.objects.create(
            classroom=classroom,
            title="Measured Assignment",
            description="Dashboard count regression coverage.",
            due_date=timezone.now() + timezone.timedelta(days=1),
        )

        CodingProblem.objects.update(is_active=False)
        problem = CodingProblem.objects.create(
            title="Measured Problem",
            topic="loops",
            description="Return one.",
            starter_code="def solve():\n    return 1\n",
            function_name="solve",
            test_cases=[{"input": [], "expected": 1}],
            difficulty=CodingProblem.DIFFICULTY_BEGINNER,
            is_active=True,
        )
        challenge_set = DailyChallengeSet.objects.create(
            student=self.student,
            date=_today(),
            solved_count=1,
            easy_solved_count=1,
        )
        DailyChallenge.objects.create(
            challenge_set=challenge_set,
            student=self.student,
            problem=problem,
            date=challenge_set.date,
            title=problem.title,
            description=problem.description,
            topic=problem.topic,
            starter_code=problem.starter_code,
            function_name=problem.function_name,
            test_cases=problem.test_cases,
            status=DailyChallenge.STATUS_SOLVED,
            score=5,
        )
        StudentPoints.objects.create(
            student=self.student,
            total_points=5,
            daily_points=5,
            points_remaining=5,
        )
        DailyChallengeSession.objects.create(
            student=self.student,
            date=challenge_set.date,
            questions_solved=1,
            points_earned=5,
            session_score=5,
        )
        self.client.force_login(self.student)

    def test_dashboard_reuses_context_data_and_stays_query_bounded(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("student_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Measured Classroom")
        self.assertContains(response, "1 assignments")
        self.assertContains(response, "1 / 1 solved")
        # Includes test-client session and middleware queries; the old
        # regeneration path exceeded 140 queries for this request.
        self.assertLessEqual(len(queries), 20)
