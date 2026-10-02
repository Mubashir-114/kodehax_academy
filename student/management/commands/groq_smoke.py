"""Opt-in provider checks using synthetic text and an in-memory image only."""
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from PIL import Image, ImageDraw

from chat.ai_service import generate_text, list_model_names, normalize_ai_exception
from chat.schemas import CHAT_SCHEMA, RUBRIC_SCHEMA
from student.services.vision import upload_image_to_ai
from teacher.services.ai_tools import generate_quiz, generate_notes, generate_coding_assignment


class Command(BaseCommand):
    help = "Check configured Groq model access and synthetic requests; prints no keys or provider bodies."

    def add_arguments(self, parser):
        parser.add_argument("--vision", action="store_true", help="Include one synthetic image query.")
        parser.add_argument("--studio", action="store_true", help="Include quiz, notes, assignment and rubric checks.")
        parser.add_argument("--vision-only", action="store_true", help="Check model access and vision without text completion.")

    def handle(self, *args, **options):
        try:
            available = set(list_model_names())
            for model in (settings.GROQ_TEXT_MODEL, settings.GROQ_VISION_MODEL):
                if model not in available:
                    raise CommandError("Configured model is not in this account's model list: " + model)
                self.stdout.write("Model listed: " + model)
            if not options["vision_only"]:
                generate_text(
                    'Explain a Python loop. Return a single JSON object with every field in this example: '
                    '{"type":"explanation","title":"Loops","content":"Explanation",'
                    '"examples":[],"quiz":[],"follow_up":[],"difficulty":"easy","tags":["loops"]}.',
                    schema=CHAT_SCHEMA,
                )
                self.stdout.write("Synthetic text chat: passed JSON validation")
            if options["studio"]:
                for label, function in (("quiz", generate_quiz), ("notes", generate_notes),
                                        ("assignment", generate_coding_assignment)):
                    output = function("Python loops: 2 questions")
                    if not output.strip():
                        raise CommandError("Empty studio response: " + label)
                    self.stdout.write("Synthetic " + label + ": passed")
                generate_text(
                    'Grade this synthetic Python code: print(1). Return only JSON with numeric '
                    'syntax, logic, structure, readability scores from 0 to 10 and a string summary.',
                    schema=RUBRIC_SCHEMA,
                )
                self.stdout.write("Synthetic grading rubric: passed JSON validation")
            if options["vision"] or options["vision_only"]:
                image = Image.new("RGB", (640, 240), "white")
                ImageDraw.Draw(image).text((30, 60), "2 + 2 = ?", fill="black", font_size=48)
                buffer = BytesIO()
                image.save(buffer, format="PNG")
                image.close()
                upload_image_to_ai(SimpleUploadedFile("synthetic.png", buffer.getvalue(), content_type="image/png"))
                self.stdout.write("Synthetic vision: passed JSON and image-response validation")
        except CommandError:
            raise
        except Exception as exc:
            # Do not print raw SDK exceptions, request headers or generated content.
            error = normalize_ai_exception(exc)
            cause = exc
            while cause.__cause__ is not None:
                cause = cause.__cause__
            status = getattr(exc.__cause__ or exc, "status_code", None)
            raise CommandError(f"Groq smoke failed: {error.code}; provider HTTP status={status}; exception={type(cause).__name__}") from None
