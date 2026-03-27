from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from teacher.models import Assignment


class Command(BaseCommand):
    help = "Re-evaluate a quiz assignment for a specific student."

    def add_arguments(self, parser):
        parser.add_argument("assignment_id", type=int, help="Quiz assignment id.")
        parser.add_argument("username", help="Student username.")

    def handle(self, *args, **options):
        assignment = self._get_assignment(options["assignment_id"])
        student = self._get_student(options["username"])
        evaluate_quiz_for_student = self._get_evaluator()

        self.stdout.write("Re-evaluating quiz...")
        result = evaluate_quiz_for_student(assignment, student)
        self.stdout.write(f"New score: {result.score} / {assignment.max_score}")

    def _get_assignment(self, assignment_id):
        try:
            return Assignment.objects.get(id=assignment_id, assignment_type="quiz")
        except Assignment.DoesNotExist as exc:
            raise CommandError(f"Quiz assignment with id {assignment_id} was not found.") from exc

    def _get_student(self, username):
        user_model = get_user_model()
        try:
            return user_model.objects.get(username=username)
        except user_model.DoesNotExist as exc:
            raise CommandError(f"User '{username}' was not found.") from exc

    def _get_evaluator(self):
        try:
            from teacher.services.evaluation import evaluate_quiz_for_student
        except ImportError as exc:
            raise CommandError(
                "Quiz evaluation dependencies are unavailable. "
                "Install the required AI packages before running this command."
            ) from exc

        return evaluate_quiz_for_student
