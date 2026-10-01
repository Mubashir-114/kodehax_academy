import re

from django.conf import settings

from chat.ai_service import AIServiceError, generate_text, normalize_ai_exception


_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


def _extract_requested_question_count(topic, default=5):
    text = (topic or "").strip().lower()
    if not text:
        return default

    # Matches patterns like "10 questions", "10 mcqs", "10 quiz questions".
    digit_match = re.search(r"\b(\d{1,2})\s*(?:question|questions|mcq|mcqs|quiz questions?)\b", text)
    if digit_match:
        value = int(digit_match.group(1))
        return max(1, min(value, 30))

    # Matches patterns like "ten questions" or "ten mcqs".
    word_match = re.search(
        r"\b(" + "|".join(_NUMBER_WORDS.keys()) + r")\s*(?:question|questions|mcq|mcqs|quiz questions?)\b",
        text,
    )
    if word_match:
        value = _NUMBER_WORDS[word_match.group(1)]
        return max(1, min(value, 30))

    return default


def _count_generated_questions(text):
    if not text:
        return 0
    matches = re.findall(r"(?im)^\s*Q\s*\d+\s*[\).:]", text)
    return len(matches)


def _configuration_error():
    if not settings.GROQ_API_KEY:
        raise AIServiceError(
            "missing_key",
            "AI key is not connected",
            "The content studio is ready, but the Groq API key is missing or not loaded.",
            "Add GROQ_API_KEY to .env and restart the Django server.",
        )


def generate_quiz(topic, requested_count=None):
    _configuration_error()

    if isinstance(requested_count, int) and requested_count > 0:
        question_count = max(1, min(requested_count, 30))
    else:
        question_count = _extract_requested_question_count(topic, default=5)
    final_q_line = f"(continue until Q{question_count})"

    prompt = f"""
You are generating a teacher-ready quiz.
Topic: {topic}

Requirements:
- Write exactly {question_count} multiple-choice questions.
- Difficulty: moderate.
- Each question must have 4 options: A, B, C, D.
- After all questions, provide a separate section named 'Answer Key'.
- Keep language concise and student-friendly.

Strict output format:
Q1. <question text>
A) ...
B) ...
C) ...
D) ...

Q2. ...

{final_q_line}

Answer Key:
1) <option letter>
2) <option letter>
... (continue sequentially until {question_count})

CRITICAL:
- Do NOT generate anything else other than these {question_count} multiple choice questions.
- The output must contain exactly {question_count} questions and exactly {question_count} answer-key lines.
"""

    try:
        first_pass = generate_text(prompt)
        if _count_generated_questions(first_pass) == question_count:
            return first_pass

        correction_prompt = f"""
You produced the wrong number of quiz questions.
Target count: exactly {question_count}.

Rewrite the quiz from scratch in the same format, and return:
- exactly {question_count} questions (Q1..Q{question_count})
- exactly {question_count} answer-key lines
- no extra commentary

Topic: {topic}
"""
        second_pass = generate_text(correction_prompt)
        if _count_generated_questions(second_pass) == question_count:
            return second_pass
        return second_pass or first_pass
    except Exception as exc:
        raise normalize_ai_exception(exc) from exc


def generate_notes(topic):
    _configuration_error()

    prompt = f"""
Create concise classroom lecture notes for: {topic}

Format with clear headings:
1. Overview
2. Core Concepts
3. Worked Example
4. Common Mistakes
5. Quick Recap

Rules:
- Use short paragraphs and bullet points where useful.
- Keep it practical for high-school/undergrad learners.
- End with 3 quick revision questions.
"""

    try:
        return generate_text(prompt)
    except Exception as exc:
        raise normalize_ai_exception(exc) from exc


def strip_quiz_answers(quiz_text):

    if not quiz_text:
        return ""

    cleaned = re.split(r"(?im)^\s*answer\s*key\s*:?\s*$", quiz_text)[0]
    cleaned = re.sub(r"(?im)^\s*(correct\s*answer|answer)\s*[:\-].*$", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()


def generate_coding_assignment(topic):
    _configuration_error()

    prompt = f"""
You are creating a standalone coding assignment for students.
Topic: {topic}

Requirements:
- Create coding problems based strictly on the topic above.
- If the topic asks for multiple problems (e.g., "3 DSA questions"), you MUST separate each problem strictly using the heading "### Problem X:" (where X is the number 1, 2, 3...).
- The assignment must include three clear sub-headings for EACH problem:
  1. Problem Statement
  2. Requirements (bullet points regarding inputs, outputs, constraints)
  3. Examples (Input & Output formats)

Format rules:
- Format the output using clear Markdown.
- Keep the language completely concise and focused.
- Do NOT provide the implementation or solution code to the problem.

CRITICAL: Provide ONLY the coding problem details. Do NOT output MCQs or notes.
"""

    try:
        return generate_text(prompt)
    except Exception as exc:
        raise normalize_ai_exception(exc) from exc
