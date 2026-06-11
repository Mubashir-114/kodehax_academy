import json

with open('daily_challenges/problems_seed.json', 'r') as f:
    data = json.load(f)

# Track unique problems by title base (without the number)
seen_problems = {}
unique_data = []

for problem in data:
    title = problem['title']
    # Extract base title (e.g., "Count Even Numbers" from "Count Even Numbers 2")
    # Try to remove trailing numbers
    import re
    base_title = re.sub(r'\s+\d+$', '', title)
    
    if base_title not in seen_problems:
        seen_problems[base_title] = title
        unique_data.append(problem)
    else:
        print(f"Skipping duplicate: {title} (first instance was: {seen_problems[base_title]})")

print(f"\nOriginal count: {len(data)}")
print(f"Unique count: {len(unique_data)}")
print(f"Removed: {len(data) - len(unique_data)} duplicates")

# Save the cleaned data
with open('daily_challenges/problems_seed.json', 'w') as f:
    json.dump(unique_data, f, indent=2)

print("\nProblems_seed.json has been updated with duplicates removed.")
