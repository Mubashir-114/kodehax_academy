import json

with open('daily_challenges/problems_seed.json', 'r') as f:
    data = json.load(f)

# Group by description and test cases to find true semantic duplicates
from collections import defaultdict

duplicates_map = defaultdict(list)

for idx, p in enumerate(data):
    # Use description and test cases as the key
    key = (p.get('description'), json.dumps(p.get('test_cases', []), sort_keys=True))
    duplicates_map[key].append((idx, p['title'], p.get('function_name'), p.get('order')))

# Find duplicate groups
duplicate_groups = {k: v for k, v in duplicates_map.items() if len(v) > 1}

print(f"Found {len(duplicate_groups)} groups of true semantic duplicates:\n")

for key, problems in duplicate_groups.items():
    desc = key[0][:70]
    print(f"Description: {desc}...")
    print(f"  {len(problems)} instances:")
    for idx, title, func, order in problems:
        print(f"    - {title} (idx: {idx}, func: {func}, order: {order})")
    print()
