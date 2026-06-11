import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodehax_academy.settings')
django.setup()

from daily_challenges.models import DailyChallenge
from skill_assessment.models import CodingProblem

# Check for orphaned DailyChallenge records
all_challenges = DailyChallenge.objects.all()
print(f"Total DailyChallenge records: {all_challenges.count()}")

# Find challenges with invalid problem references
orphaned = []
for challenge in all_challenges:
    try:
        _ = challenge.problem
    except CodingProblem.DoesNotExist:
        orphaned.append(challenge.id)

print(f"Orphaned DailyChallenge records (referencing deleted problems): {len(orphaned)}")
if orphaned:
    print(f"IDs: {orphaned[:10]}...")  # Show first 10
    # Delete orphaned records
    DailyChallenge.objects.filter(id__in=orphaned).delete()
    print(f"Deleted {len(orphaned)} orphaned records")

# Delete all remaining challenges to be safe
remaining_count = DailyChallenge.objects.count()
if remaining_count > 0:
    DailyChallenge.objects.all().delete()
    print(f"Deleted remaining {remaining_count} DailyChallenge records")

print(f"\nFinal DailyChallenge count: {DailyChallenge.objects.count()}")
