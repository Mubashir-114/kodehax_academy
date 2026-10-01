from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from code_execution.service import execute, ExecutionUnavailable


class Command(BaseCommand):
    help = "Opt-in synthetic remote executor transport check; does not certify sandbox isolation."

    def handle(self, *args, **options):
        if settings.CODE_EXECUTION_BACKEND != "remote":
            raise CommandError("Configure the remote backend; a local subprocess is not isolated execution.")
        try:
            result = execute("def synthetic_add(a, b):\n    return a + b", "synthetic_add",
                             [{"input": [2, 2], "expected": 4}], kind="daily")
        except ExecutionUnavailable:
            raise CommandError("Remote executor is unavailable or failed protocol validation.") from None
        if result["fatal_error"] or not all(row["passed"] for row in result["results"]):
            raise CommandError("Synthetic evaluation failed.")
        self.stdout.write("Remote transport and synthetic evaluation passed. Infrastructure isolation still requires independent verification.")
