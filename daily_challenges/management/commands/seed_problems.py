import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from skill_assessment.models import CodingProblem


class Command(BaseCommand):
    help = "Seed the daily challenge CodingProblem pool from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default="daily_challenges/problems_seed.json",
            help="Path to a JSON file containing CodingProblem rows.",
        )

    def handle(self, *args, **options):
        seed_path = Path(options["path"])
        if not seed_path.is_absolute():
            seed_path = Path.cwd() / seed_path
        if not seed_path.exists():
            raise CommandError(f"Seed file not found: {seed_path}")

        try:
            problems = json.loads(seed_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {seed_path}: {exc}") from exc

        if not isinstance(problems, list):
            raise CommandError("Seed file must contain a JSON list.")

        allowed_fields = {
            "title",
            "topic",
            "description",
            "starter_code",
            "function_name",
            "test_cases",
            "hint1",
            "hint2",
            "difficulty",
            "order",
            "is_active",
        }
        created = 0
        updated = 0
        difficulty_counts = {}
        topic_counts = {}

        for index, raw_problem in enumerate(problems, start=1):
            if not isinstance(raw_problem, dict):
                raise CommandError(f"Problem #{index} must be an object.")
            missing = {"title", "description", "function_name", "test_cases", "difficulty"} - set(raw_problem)
            if missing:
                raise CommandError(f"Problem #{index} is missing fields: {', '.join(sorted(missing))}")

            payload = {key: value for key, value in raw_problem.items() if key in allowed_fields}
            payload.setdefault("topic", "general")
            payload.setdefault("starter_code", "")
            payload.setdefault("hint1", "")
            payload.setdefault("hint2", "")
            payload.setdefault("order", index)
            payload.setdefault("is_active", True)

            title = payload.pop("title")
            problem, was_created = CodingProblem.objects.get_or_create(
                title=title,
                defaults=payload,
            )
            if was_created:
                created += 1
            else:
                for field, value in payload.items():
                    setattr(problem, field, value)
                problem.save()
                updated += 1

            difficulty_counts[problem.difficulty] = difficulty_counts.get(problem.difficulty, 0) + 1
            topic_counts[problem.topic] = topic_counts.get(problem.topic, 0) + 1

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(problems)} problems: {created} created, {updated} updated."))
        self.stdout.write("By difficulty: " + json.dumps(difficulty_counts, sort_keys=True))
        self.stdout.write("By topic: " + json.dumps(topic_counts, sort_keys=True))
