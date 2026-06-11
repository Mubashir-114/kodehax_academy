import json

with open('daily_challenges/problems_seed.json', 'r') as f:
    data = json.load(f)

# Find problems with "Count Even" in title
count_even = [p for p in data if 'Count Even' in p['title']]
print(f'Found {len(count_even)} Count Even problems:')
for i, p in enumerate(count_even, 1):
    print(f"{i}. Title: {p['title']}")
    print(f"   Order: {p.get('order')}")
    print(f"   Function: {p.get('function_name')}")
    print(f"   Description: {p['description'][:60]}...")
    print()

# Find problems with "Is Prime" in title  
is_prime = [p for p in data if 'Is Prime' in p['title']]
print(f'\nFound {len(is_prime)} Is Prime problems:')
for i, p in enumerate(is_prime, 1):
    print(f"{i}. Title: {p['title']}")
    print(f"   Order: {p.get('order')}")
    print(f"   Function: {p.get('function_name')}")
    print()

# Check for duplicate function names
all_functions = [p.get('function_name') for p in data]
from collections import Counter
dupes = {fn: c for fn, c in Counter(all_functions).items() if c > 1}
print(f'\nDuplicate function names:')
for fn, count in sorted(dupes.items()):
    print(f"  {fn}: {count} times")
