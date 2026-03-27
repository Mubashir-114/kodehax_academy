from django.core.management.base import BaseCommand

from teacher.models import Assignment


class Command(BaseCommand):
    help = "Print recent quiz assignments and their questions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=2,
            help="Number of recent quiz assignments to inspect.",
        )

    def handle(self, *args, **options):
        limit = max(options["limit"], 1)
        assignments = Assignment.objects.filter(assignment_type="quiz").order_by("-id")[:limit]

        if not assignments:
            self.stdout.write(self.style.WARNING("No quiz assignments found."))
            return

        for assignment in assignments:
            self.stdout.write(f"Assignment {assignment.id}: {assignment.title}")
            for question in assignment.quiz_questions.all():
                self.stdout.write(f"  Q{question.id}: {question.question[:40]}...")
                self.stdout.write(f"    A: '{question.option_a}'")
                self.stdout.write(f"    B: '{question.option_b}'")
                self.stdout.write(f"    C: '{question.option_c}'")
                self.stdout.write(f"    D: '{question.option_d}'")
            self.stdout.write("-" * 40)

