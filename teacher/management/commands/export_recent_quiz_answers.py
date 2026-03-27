from pathlib import Path

from django.core.management.base import BaseCommand

from teacher.models import QuizAnswer


class Command(BaseCommand):
    help = "Export recent quiz answers to a text file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Number of recent quiz answers to export.",
        )
        parser.add_argument(
            "--output",
            default="ans_debug.txt",
            help="Destination file path for the exported answers.",
        )

    def handle(self, *args, **options):
        limit = max(options["limit"], 1)
        output_path = Path(options["output"])
        answers = QuizAnswer.objects.select_related("student", "question").order_by("-id")[:limit]

        with output_path.open("w", encoding="utf-8") as output_file:
            for answer in answers:
                output_file.write(
                    f"Answer {answer.id} - Student: {answer.student.username} - "
                    f"QID: {answer.question.id} - Option: '{answer.selected_option}'\n"
                )

        self.stdout.write(self.style.SUCCESS(f"Exported {len(answers)} answers to {output_path}."))

