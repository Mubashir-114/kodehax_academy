import json

with open('daily_challenges/problems_seed.json', 'r') as f:
    data = json.load(f)

print(f'Seed file contains {len(data)} unique problems:\n')
for i, p in enumerate(data, 1):
    print(f'{i:2}. {p["title"]}')

# Check for any duplicates
from collections import Counter
titles = [p['title'] for p in data]
dupes = {t: c for t, c in Counter(titles).items() if c > 1}
if dupes:
    print('\n\nDUPLICATES FOUND:')
    for title, count in dupes.items():
        print(f'  {title}: {count} times')
else:
    print('\n\nNo duplicates found - all problems are unique!')
