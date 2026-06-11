import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodehax_academy.settings')
django.setup()

from django.contrib.auth import get_user_model
from daily_challenges.services import generate_daily_challenges
from datetime import date

User = get_user_model()

# Get all active students
students = User.objects.filter(role='student', is_active=True)
print(f"Found {students.count()} active students")

# Generate fresh daily challenges for each student for today
today = date.today()
generated_count = 0

for student in students:
    try:
        challenge_set = generate_daily_challenges(student, challenge_date=today, force=True)
        print(f"✓ Generated {challenge_set.challenges.count()} challenges for {student.username}")
        generated_count += 1
    except Exception as e:
        print(f"✗ Error generating challenges for {student.username}: {e}")

print(f"\nSuccessfully generated challenges for {generated_count}/{students.count()} students")
