import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodehax_academy.settings')
django.setup()

from skill_assessment.models import CodingProblem

# Delete ALL CodingProblems
count = CodingProblem.objects.count()
CodingProblem.objects.all().delete()
print(f"Deleted {count} problems from database")
print("Database cleared - ready to reseed")
