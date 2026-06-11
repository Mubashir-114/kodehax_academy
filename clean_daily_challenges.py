import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodehax_academy.settings')
django.setup()

from daily_challenges.models import DailyChallenge, DailyChallengeSet, DailyChallengeSession, StudentChallengeAttempt, StudentPoints

# Delete all daily challenge related records
attempts_count = StudentChallengeAttempt.objects.count()
StudentChallengeAttempt.objects.all().delete()
print(f"Deleted {attempts_count} StudentChallengeAttempt records")

points_count = StudentPoints.objects.count()
StudentPoints.objects.all().delete()
print(f"Deleted {points_count} StudentPoints records")

sessions_count = DailyChallengeSession.objects.count()
DailyChallengeSession.objects.all().delete()
print(f"Deleted {sessions_count} DailyChallengeSession records")

challenges_count = DailyChallenge.objects.count()
DailyChallenge.objects.all().delete()
print(f"Deleted {challenges_count} DailyChallenge records")

sets_count = DailyChallengeSet.objects.count()
DailyChallengeSet.objects.all().delete()
print(f"Deleted {sets_count} DailyChallengeSet records")

print("\nAll daily challenge data cleaned up!")
