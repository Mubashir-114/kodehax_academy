import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodehax_academy.settings')
django.setup()

from skill_assessment.models import CodingProblem

# Delete all CodingProblems
count = CodingProblem.objects.count()
CodingProblem.objects.all().delete()
print(f"Deleted {count} problems from database")
print("Ready to reseed with clean data")
