import ast
import json
import subprocess
import sys
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from .models import AssessmentQuestion, CodingProblem, StudentAssessment, StudentSkill


DEFAULT_QUESTIONS = [
    {
        "question_text": "Which data structure stores elements in contiguous memory and allows index-based access?",
        "topic": "arrays",
        "difficulty": "beginner",
        "correct_answer": "A",
        "options": [
            {"value": "A", "label": "Array"},
            {"value": "B", "label": "Queue"},
            {"value": "C", "label": "Stack"},
            {"value": "D", "label": "Tree"},
        ],
    },
    {
        "question_text": "What is the time complexity of binary search on a sorted array?",
        "topic": "time complexity",
        "difficulty": "basic",
        "correct_answer": "B",
        "options": [
            {"value": "A", "label": "O(n)"},
            {"value": "B", "label": "O(log n)"},
            {"value": "C", "label": "O(n log n)"},
            {"value": "D", "label": "O(1)"},
        ],
    },
    {
        "question_text": "Which loop is best when you know exactly how many times code should repeat?",
        "topic": "loops",
        "difficulty": "beginner",
        "correct_answer": "C",
        "options": [
            {"value": "A", "label": "while loop"},
            {"value": "B", "label": "do-while loop"},
            {"value": "C", "label": "for loop"},
            {"value": "D", "label": "infinite loop"},
        ],
    },
    {
        "question_text": "What is recursion?",
        "topic": "recursion",
        "difficulty": "beginner",
        "correct_answer": "D",
        "options": [
            {"value": "A", "label": "A loop that always runs forever"},
            {"value": "B", "label": "Sorting items alphabetically"},
            {"value": "C", "label": "A variable calling another variable"},
            {"value": "D", "label": "A function calling itself with a smaller subproblem"},
        ],
    },
    {
        "question_text": "Which sorting algorithm has average-case time complexity O(n log n)?",
        "topic": "sorting",
        "difficulty": "basic",
        "correct_answer": "A",
        "options": [
            {"value": "A", "label": "Merge sort"},
            {"value": "B", "label": "Bubble sort"},
            {"value": "C", "label": "Selection sort"},
            {"value": "D", "label": "Linear search"},
        ],
    },
    {
        "question_text": "What does `s[::-1]` do in Python?",
        "topic": "strings",
        "difficulty": "beginner",
        "correct_answer": "B",
        "options": [
            {"value": "A", "label": "Returns every second character"},
            {"value": "B", "label": "Reverses the string"},
            {"value": "C", "label": "Sorts the string"},
            {"value": "D", "label": "Removes duplicates"},
        ],
    },
    {
        "question_text": "If an algorithm inspects every element of a list once, what is its time complexity?",
        "topic": "time complexity",
        "difficulty": "beginner",
        "correct_answer": "A",
        "options": [
            {"value": "A", "label": "O(n)"},
            {"value": "B", "label": "O(log n)"},
            {"value": "C", "label": "O(n^2)"},
            {"value": "D", "label": "O(1)"},
        ],
    },
    {
        "question_text": "Which statement about arrays is true?",
        "topic": "arrays",
        "difficulty": "basic",
        "correct_answer": "C",
        "options": [
            {"value": "A", "label": "Arrays cannot store numbers"},
            {"value": "B", "label": "Arrays always remove duplicate values"},
            {"value": "C", "label": "Arrays can be traversed using indexes"},
            {"value": "D", "label": "Arrays are only available in Python"},
        ],
    },
    {
        "question_text": "Why is a base case important in recursion?",
        "topic": "recursion",
        "difficulty": "basic",
        "correct_answer": "B",
        "options": [
            {"value": "A", "label": "It makes the function run faster than O(1)"},
            {"value": "B", "label": "It stops recursive calls from continuing forever"},
            {"value": "C", "label": "It sorts the recursion output"},
            {"value": "D", "label": "It converts recursion into iteration"},
        ],
    },
    {
        "question_text": "Which built-in Python method joins a list of strings into a single string?",
        "topic": "strings",
        "difficulty": "beginner",
        "correct_answer": "D",
        "options": [
            {"value": "A", "label": "split()"},
            {"value": "B", "label": "append()"},
            {"value": "C", "label": "replace()"},
            {"value": "D", "label": "join()"},
        ],
    },
]


DEFAULT_PROBLEMS = [
    {
        "title": "Reverse a String",
        "topic": "strings",
        "description": (
            "Write a Python function `reverse_string(text)` that returns the reversed "
            "version of the input string."
        ),
        "function_name": "reverse_string",
        "difficulty": "beginner",
        "starter_code": (
            "def reverse_string(text):\n"
            "    # Return the reversed string.\n"
            "    return text[::-1]\n"
        ),
        "test_cases": [
            {"input": ["hello"], "expected": "olleh"},
            {"input": ["Kodehax"], "expected": "xahedoK"},
            {"input": [""], "expected": ""},
        ],
    },
    {
        "title": "Sum of an Array",
        "topic": "arrays",
        "description": (
            "Write a Python function `sum_array(numbers)` that returns the total "
            "sum of all numbers in the list."
        ),
        "function_name": "sum_array",
        "difficulty": "beginner",
        "starter_code": (
            "def sum_array(numbers):\n"
            "    # Return the sum of the list.\n"
            "    return sum(numbers)\n"
        ),
        "test_cases": [
            {"input": [[1, 2, 3, 4]], "expected": 10},
            {"input": [[5]], "expected": 5},
            {"input": [[-2, 4, 8]], "expected": 10},
        ],
    },
    {
        "title": "Find Maximum in a List",
        "topic": "arrays",
        "description": (
            "Write a Python function `max_in_list(numbers)` that returns the largest "
            "number from the given list."
        ),
        "function_name": "max_in_list",
        "difficulty": "beginner",
        "starter_code": (
            "def max_in_list(numbers):\n"
            "    # Return the largest value in the list.\n"
            "    return max(numbers)\n"
        ),
        "test_cases": [
            {"input": [[3, 8, 2, 9, 4]], "expected": 9},
            {"input": [[-5, -2, -8]], "expected": -2},
            {"input": [[7]], "expected": 7},
        ],
    },
    {
        "title": "Count Even Numbers",
        "topic": "loops",
        "description": (
            "Write a Python function `count_even_numbers(numbers)` that returns how "
            "many even values are present in the list."
        ),
        "function_name": "count_even_numbers",
        "difficulty": "basic",
        "starter_code": (
            "def count_even_numbers(numbers):\n"
            "    count = 0\n"
            "    for value in numbers:\n"
            "        if value % 2 == 0:\n"
            "            count += 1\n"
            "    return count\n"
        ),
        "test_cases": [
            {"input": [[1, 2, 3, 4, 5, 6]], "expected": 3},
            {"input": [[7, 9, 11]], "expected": 0},
            {"input": [[2, 2, 2]], "expected": 3},
        ],
    },
    {
        "title": "Count Vowels",
        "topic": "strings",
        "description": (
            "Write a Python function `count_vowels(text)` that returns the number of "
            "vowels in the input string."
        ),
        "function_name": "count_vowels",
        "difficulty": "basic",
        "starter_code": (
            "def count_vowels(text):\n"
            "    vowels = 'aeiouAEIOU'\n"
            "    count = 0\n"
            "    for char in text:\n"
            "        if char in vowels:\n"
            "            count += 1\n"
            "    return count\n"
        ),
        "test_cases": [
            {"input": ["Kodehax Academy"], "expected": 6},
            {"input": ["rhythm"], "expected": 0},
            {"input": ["AEIOU"], "expected": 5},
        ],
    },
    {
        "title": "Factorial Using Recursion",
        "topic": "recursion",
        "description": (
            "Write a Python function `factorial_recursive(n)` that returns the "
            "factorial of `n` using recursion."
        ),
        "function_name": "factorial_recursive",
        "difficulty": "intermediate",
        "starter_code": (
            "def factorial_recursive(n):\n"
            "    if n <= 1:\n"
            "        return 1\n"
            "    return n * factorial_recursive(n - 1)\n"
        ),
        "test_cases": [
            {"input": [1], "expected": 1},
            {"input": [4], "expected": 24},
            {"input": [6], "expected": 720},
        ],
    },
    {
        "title": "Sort Numbers",
        "topic": "sorting",
        "description": (
            "Write a Python function `sort_numbers(numbers)` that returns the list "
            "in ascending order."
        ),
        "function_name": "sort_numbers",
        "difficulty": "intermediate",
        "starter_code": (
            "def sort_numbers(numbers):\n"
            "    return sorted(numbers)\n"
        ),
        "test_cases": [
            {"input": [[4, 1, 3, 2]], "expected": [1, 2, 3, 4]},
            {"input": [[9, 7, 9, 1]], "expected": [1, 7, 9, 9]},
            {"input": [[5]], "expected": [5]},
        ],
    },
    {
        "title": "Binary Search Index",
        "topic": "time complexity",
        "description": (
            "Write a Python function `binary_search_index(numbers, target)` that "
            "returns the index of `target` in a sorted list, or `-1` if not found."
        ),
        "function_name": "binary_search_index",
        "difficulty": "advanced",
        "starter_code": (
            "def binary_search_index(numbers, target):\n"
            "    left = 0\n"
            "    right = len(numbers) - 1\n"
            "    while left <= right:\n"
            "        mid = (left + right) // 2\n"
            "        if numbers[mid] == target:\n"
            "            return mid\n"
            "        if numbers[mid] < target:\n"
            "            left = mid + 1\n"
            "        else:\n"
            "            right = mid - 1\n"
            "    return -1\n"
        ),
        "test_cases": [
            {"input": [[1, 3, 5, 7, 9], 7], "expected": 3},
            {"input": [[2, 4, 6, 8], 5], "expected": -1},
            {"input": [[10, 20, 30], 10], "expected": 0},
        ],
    },
    {
        "title": "Recursive Fibonacci",
        "topic": "recursion",
        "description": (
            "Write a Python function `fibonacci_number(n)` that returns the nth "
            "Fibonacci number using recursion."
        ),
        "function_name": "fibonacci_number",
        "difficulty": "advanced",
        "starter_code": (
            "def fibonacci_number(n):\n"
            "    if n <= 1:\n"
            "        return n\n"
            "    return fibonacci_number(n - 1) + fibonacci_number(n - 2)\n"
        ),
        "test_cases": [
            {"input": [0], "expected": 0},
            {"input": [5], "expected": 5},
            {"input": [7], "expected": 13},
        ],
    },
]


SELF_ASSESSMENT_WEIGHTS = {
    "programming_language_familiarity": {
        "beginner": 10,
        "intermediate": 30,
        "advanced": 50,
    },
    "coding_experience_duration": {
        "new": 5,
        "less_than_6m": 12,
        "6_to_12m": 20,
        "1_to_2y": 30,
        "2y_plus": 40,
    },
    "confidence_rating": {
        "1": 4,
        "2": 8,
        "3": 12,
        "4": 16,
        "5": 20,
    },
}

SELF_ASSESSMENT_PLATFORM_POINTS = 5
SELF_ASSESSMENT_PLATFORM_MAX = 20
MCQ_CORRECT_POINTS = 5
CODING_FULL_POINTS = 20
CODING_PARTIAL_POINTS = 10
CODING_LOGIC_PARTIAL_POINTS = 8

LOGIC_HINTS = {
    "reverse_string": ("[::-1]", "reversed(", "join(", "for ", "range("),
    "sum_array": ("sum(", "for ", "+=", "total"),
    "max_in_list": ("max(", "for ", "if ", ">", "largest", "current_max"),
    "count_even_numbers": ("for ", "% 2", "count", "if "),
    "count_vowels": ("for ", "in vowels", "count", "aeiou"),
    "factorial_recursive": ("factorial_recursive(", "return", "*", "if "),
    "sort_numbers": ("sorted(", ".sort(", "for ", "while "),
    "binary_search_index": ("while ", "mid", "left", "right"),
    "fibonacci_number": ("fibonacci_number(", "return", "+", "if "),
}


def build_starter_template(function_name, starter_code=""):
    signature_line = f"def {function_name}(...):"
    for line in (starter_code or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"def {function_name}(") and stripped.endswith(":"):
            signature_line = stripped
            break
    return f"{signature_line}\n    # Write your solution here\n    pass\n"

RUNNER_SCRIPT = r"""
import ast
import builtins
import contextlib
import io
import json
import sys

payload = json.loads(sys.stdin.read())
code = payload["code"]
function_name = payload["function_name"]
test_cases = payload["test_cases"]

blocked_calls = {"eval", "exec", "open", "__import__", "compile", "input", "globals", "locals", "vars"}
blocked_modules = {"os", "sys", "subprocess", "socket", "pathlib", "shutil"}

tree = ast.parse(code, mode="exec")
for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        else:
            if node.module:
                names = [node.module.split(".")[0]]
        if any(name in blocked_modules for name in names):
            raise ValueError("Restricted import detected.")
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id in blocked_calls:
            raise ValueError("Restricted call detected.")
    if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
        raise ValueError("Dunder attribute access is not allowed.")

captured_stdout = io.StringIO()

def safe_print(*args, **kwargs):
    kwargs.setdefault("file", captured_stdout)
    return builtins.print(*args, **kwargs)

allowed_builtins = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": safe_print,
    "range": range,
    "reversed": reversed,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}

namespace = {"__builtins__": allowed_builtins}
with contextlib.redirect_stdout(captured_stdout):
    exec(compile(tree, "<student-code>", "exec"), namespace, namespace)

target = namespace.get(function_name)
if not callable(target):
    raise ValueError(f"Function '{function_name}' was not defined.")

results = []
for case in test_cases:
    args = case.get("input", [])
    expected = case.get("expected")
    actual = target(*args)
    results.append({"passed": actual == expected, "actual": actual, "expected": expected})

sys.stdout.write(json.dumps({"results": results}))
"""


def ensure_default_assessment_content():
    for index, item in enumerate(DEFAULT_QUESTIONS, start=1):
        AssessmentQuestion.objects.update_or_create(
            question_text=item["question_text"],
            defaults={
                "topic": item["topic"],
                "difficulty": item["difficulty"],
                "correct_answer": item["correct_answer"],
                "options": item["options"],
                "order": index,
                "is_active": True,
            },
        )

    for index, item in enumerate(DEFAULT_PROBLEMS, start=1):
        CodingProblem.objects.update_or_create(
            title=item["title"],
            defaults={
                "topic": item["topic"],
                "description": item["description"],
                "starter_code": build_starter_template(item["function_name"], item["starter_code"]),
                "function_name": item["function_name"],
                "test_cases": item["test_cases"],
                "difficulty": item["difficulty"],
                "order": index,
                "is_active": True,
            },
        )


def calculate_self_assessment_score(cleaned_data):
    familiarity_score = SELF_ASSESSMENT_WEIGHTS["programming_language_familiarity"].get(
        cleaned_data["programming_language_familiarity"],
        0,
    )
    experience_score = SELF_ASSESSMENT_WEIGHTS["coding_experience_duration"].get(
        cleaned_data["coding_experience_duration"],
        0,
    )
    confidence_score = SELF_ASSESSMENT_WEIGHTS["confidence_rating"].get(
        cleaned_data["confidence_rating"],
        0,
    )
    platform_score = min(
        len(cleaned_data.get("platforms_used", [])) * SELF_ASSESSMENT_PLATFORM_POINTS,
        SELF_ASSESSMENT_PLATFORM_MAX,
    )

    raw_score = familiarity_score + experience_score + confidence_score + platform_score
    return min(raw_score, 100)


def evaluate_mcq_responses(questions, cleaned_data):
    total_score = 0
    topic_breakdown = {}
    answers = {}

    for question in questions:
        field_name = f"question_{question.id}"
        selected = cleaned_data[field_name]
        is_correct = selected == question.correct_answer
        answers[str(question.id)] = selected
        total_score += MCQ_CORRECT_POINTS if is_correct else 0

        topic_stats = topic_breakdown.setdefault(
            question.topic,
            {"correct": 0, "total": 0, "status": "medium"},
        )
        topic_stats["total"] += 1
        if is_correct:
            topic_stats["correct"] += 1

    for topic, stats in topic_breakdown.items():
        accuracy = stats["correct"] / stats["total"] if stats["total"] else 0
        if accuracy >= 0.8:
            status = "strong"
        elif accuracy >= 0.5:
            status = "medium"
        else:
            status = "weak"
        stats["accuracy"] = round(accuracy * 100, 2)
        stats["status"] = status

    max_score = max(len(questions) * MCQ_CORRECT_POINTS, 1)
    normalized_score = (Decimal(total_score) / Decimal(max_score)) * Decimal("100")
    return {
        "score": total_score,
        "normalized_score": quantize_score(normalized_score),
        "answers": answers,
        "topic_breakdown": topic_breakdown,
    }


def evaluate_coding_responses(problems, cleaned_data):
    answers = {}
    breakdown = {}
    raw_score = 0

    for problem in problems:
        field_name = f"problem_{problem.id}"
        code = cleaned_data[field_name].rstrip()
        answers[str(problem.id)] = code
        case_results, execution_error = run_code_against_test_cases(problem, code)

        passed_count = sum(1 for item in case_results if item.get("passed"))
        total_count = len(case_results)
        if total_count and passed_count == total_count and not execution_error:
            problem_score = CODING_FULL_POINTS
            status = "passed"
        elif passed_count > 0:
            problem_score = CODING_PARTIAL_POINTS
            status = "partial"
        else:
            logic_score = estimate_logic_score(problem, code)
            if logic_score > 0:
                problem_score = logic_score
                status = "logic-partial"
            else:
                problem_score = 0
                status = "failed"

        raw_score += problem_score
        breakdown[str(problem.id)] = {
            "title": problem.title,
            "status": status,
            "score": problem_score,
            "passed_count": passed_count,
            "total_count": total_count,
            "results": case_results,
            "error": execution_error,
        }

    max_score = max(len(problems) * CODING_FULL_POINTS, 1)
    normalized_score = (Decimal(raw_score) / Decimal(max_score)) * Decimal("100")
    return {
        "score": raw_score,
        "normalized_score": quantize_score(normalized_score),
        "answers": answers,
        "breakdown": breakdown,
    }


def run_code_against_test_cases(problem, code):
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", RUNNER_SCRIPT],
            input=json.dumps(
                {
                    "code": code,
                    "function_name": problem.function_name,
                    "test_cases": problem.test_cases,
                }
            ),
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [], "Execution timed out."

    if completed.returncode != 0:
        return [], (completed.stderr or completed.stdout or "Execution failed.").strip()

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return [], "Execution returned an invalid response."

    return payload.get("results", []), None


def estimate_logic_score(problem, code):
    normalized_code = (code or "").strip()
    if not normalized_code:
        return 0

    score = 0
    lowered = normalized_code.lower()

    if f"def {problem.function_name.lower()}" in lowered:
        score += 3
    if "return" in lowered:
        score += 2

    hint_matches = sum(
        1 for token in LOGIC_HINTS.get(problem.function_name, ()) if token.lower() in lowered
    )
    score += min(hint_matches, 2) * 2

    try:
        tree = ast.parse(normalized_code, mode="exec")
    except SyntaxError:
        if ":" in normalized_code and "\n" in normalized_code:
            score += 1
        return min(score, CODING_LOGIC_PARTIAL_POINTS)

    function_defs = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == problem.function_name
    ]
    if function_defs:
        score += 2

    if any(isinstance(node, (ast.For, ast.While, ast.If)) for node in ast.walk(tree)):
        score += 1
    if any(isinstance(node, ast.Call) for node in ast.walk(tree)):
        score += 1

    return min(score, CODING_PARTIAL_POINTS)


def quantize_score(value):
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_final_skill_score(self_score, mcq_normalized_score, coding_normalized_score):
    final_score = (
        Decimal(str(self_score)) * Decimal("0.2")
        + Decimal(str(mcq_normalized_score)) * Decimal("0.3")
        + Decimal(str(coding_normalized_score)) * Decimal("0.5")
    )
    return quantize_score(final_score)


def classify_skill_level(score):
    numeric_score = Decimal(str(score))
    if numeric_score < Decimal("30"):
        return StudentSkill.LEVEL_BEGINNER
    if numeric_score < Decimal("50"):
        return StudentSkill.LEVEL_BASIC
    if numeric_score < Decimal("75"):
        return StudentSkill.LEVEL_INTERMEDIATE
    if numeric_score < Decimal("90"):
        return StudentSkill.LEVEL_ADVANCED
    return StudentSkill.LEVEL_EXPERT


def derive_topic_summary(topic_breakdown):
    weak_topics = {}
    strong_topics = []
    medium_topics = []

    # Defensive check: ensure topic_breakdown is a dict
    if not isinstance(topic_breakdown, dict):
        return weak_topics, strong_topics, medium_topics

    for topic, stats in topic_breakdown.items():
        # Defensive check: ensure stats is a dict
        if not isinstance(stats, dict):
            continue
        
        status = stats.get("status", "medium")
        if status == "weak":
            weak_topics[topic] = stats
        elif status == "strong":
            strong_topics.append(topic.title())
        else:
            medium_topics.append(topic.title())

    return weak_topics, strong_topics, medium_topics


def finalize_assessment(assessment):
    weak_topics, strong_topics, medium_topics = derive_topic_summary(assessment.mcq_breakdown)
    final_score = calculate_final_skill_score(
        assessment.self_assessment_score,
        assessment.mcq_score,
        assessment.coding_score,
    )
    skill_level = classify_skill_level(final_score)

    assessment.score = final_score
    assessment.completed = True
    assessment.current_step = 3
    assessment.date_completed = timezone.now()
    assessment.save(
        update_fields=[
            "score",
            "completed",
            "current_step",
            "date_completed",
            "updated_at",
        ]
    )

    StudentSkill.objects.update_or_create(
        student=assessment.student,
        defaults={
            "skill_score": final_score,
            "skill_level": skill_level,
            "weak_topics": weak_topics,
            "strong_topics": strong_topics,
            "assessment_snapshot": {
                "self_assessment_score": assessment.self_assessment_score,
                "mcq_score": assessment.mcq_score,
                "coding_score": assessment.coding_score,
                "medium_topics": medium_topics,
                "mcq_breakdown": assessment.mcq_breakdown,
                "coding_breakdown": assessment.coding_breakdown,
            },
        },
    )
    return final_score, skill_level, weak_topics, strong_topics, medium_topics


def reset_student_assessment(student):
    StudentAssessment.objects.update_or_create(
        student=student,
        defaults={
            "score": 0,
            "completed": False,
            "date_completed": None,
            "current_step": 1,
            "self_assessment_answers": {},
            "self_assessment_score": 0,
            "mcq_answers": {},
            "mcq_score": 0,
            "mcq_breakdown": {},
            "coding_answers": {},
            "coding_score": 0,
            "coding_breakdown": {},
        },
    )
    StudentSkill.objects.filter(student=student).delete()
