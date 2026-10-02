from __future__ import annotations

import json
import os
import re
from typing import Any

from teacher.models import Assignment, CodeSubmission, QuizAnswer, QuizResult, Submission
from chat.schemas import RUBRIC_SCHEMA
from chat.ai_service import ai_error_payload, generate_text


def clamp_score(score: float, max_score: float) -> float:
    if score < 0:
        return 0.0
    if score > max_score:
        return float(max_score)
    return float(score)


def parse_score(raw_score: Any, max_score: float) -> float:
    return clamp_score(float(raw_score), max_score)


def grade_file_submission_manual(submission: Submission, score: Any, feedback: str) -> Submission:
    submission.score = parse_score(score, submission.assignment.max_score)
    submission.ai_feedback = (feedback or "").strip()
    submission.save(update_fields=["score", "ai_feedback"])
    from teacher.services.performance import sync_file_submission_record

    sync_file_submission_record(submission, evaluation_type="manual")
    return submission


def grade_code_submission_manual(code_submission: CodeSubmission, score: Any, feedback: str) -> CodeSubmission:
    code_submission.score = parse_score(score, code_submission.assignment.max_score)
    code_submission.ai_feedback = (feedback or "").strip()
    code_submission.save(update_fields=["score", "ai_feedback"])
    from teacher.services.performance import sync_code_submission_record

    sync_code_submission_record(code_submission, evaluation_type="manual")
    return code_submission


_TEXT_EXTENSIONS = {".txt", ".md", ".py", ".csv", ".json", ".html", ".js", ".java", ".c", ".cpp"}


def _read_text_file(uploaded_file, char_limit: int = 6000) -> str:
    """Extract text through Django's storage API without a local path.

    ``FieldFile.path`` only exists for filesystem-backed storage, so remote
    (e.g. S3) submissions are read via ``FieldFile.open``. The extension
    whitelist, UTF-8 ``errors="ignore"`` decoding, and bounded read are kept
    the same as before.
    """
    if not uploaded_file:
        return ""
    _, ext = os.path.splitext((getattr(uploaded_file, "name", "") or "").lower())
    if ext not in _TEXT_EXTENSIONS:
        return ""
    try:
        with uploaded_file.open("rb") as handle:
            raw = handle.read(char_limit)
    except (OSError, ValueError):
        return ""
    return raw.decode("utf-8", errors="ignore")[:char_limit]


def _ai_grade(prompt: str, max_score: float) -> tuple[float, str]:
    try:
        content = generate_text(prompt).strip()
    except Exception as exc:  # noqa: BLE001
        error = ai_error_payload(exc)
        return 0.0, f"{error['title']}\n{error['message']}\nSuggestion: {error['suggestion']}"

    score_value = 0.0
    for token in content.replace("\n", " ").split():
        cleaned = token.strip().strip(",.;")
        try:
            score_value = float(cleaned)
            break
        except ValueError:
            continue
    score_value = clamp_score(score_value, max_score)
    return score_value, content


def _extract_json_dict(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Best effort extraction when the model wraps JSON with explanation.
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_rubric_score(value: Any, maximum: float = 10.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if numeric < 0:
        return 0.0
    if numeric > maximum:
        return maximum
    return numeric


def _is_ai_service_feedback(feedback: str) -> bool:
    return (feedback or "").startswith((
        "AI service is busy",
        "AI service is temporarily unavailable",
    ))


def _check_python_syntax(code: str) -> tuple[bool, str]:
    try:
        compile(code or "", "<student_submission>", "exec")
        return True, ""
    except SyntaxError as exc:
        return False, f"Line {exc.lineno}: {exc.msg}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def grade_file_submission_ai(submission: Submission) -> Submission:
    file_text = _read_text_file(submission.file)
    prompt = (
        "You are grading a student file submission.\n"
        f"Assignment description:\n{submission.assignment.description}\n\n"
        f"Student username: {submission.student.username}\n"
        f"Max score: {submission.assignment.max_score}\n"
        "Return feedback with the score as the first numeric value.\n"
        "If file text is unavailable, still provide best-effort feedback.\n\n"
        f"Extracted file text:\n{file_text or '[Non-text file or empty extract]'}"
    )
    score, feedback = _ai_grade(prompt, submission.assignment.max_score)
    submission.score = score
    submission.ai_feedback = feedback
    submission.save(update_fields=["score", "ai_feedback"])
    from teacher.services.performance import sync_file_submission_record

    sync_file_submission_record(submission, evaluation_type="ai")
    return submission


def grade_code_submission_ai(code_submission: CodeSubmission) -> CodeSubmission:
    language = (code_submission.language or "").strip().lower()
    syntax_ok = True
    syntax_error_message = ""
    if language in {"python", "py"}:
        syntax_ok, syntax_error_message = _check_python_syntax(code_submission.code)

    prompt = (
        "You are grading a coding submission using a rubric.\n"
        f"Assignment description:\n{code_submission.assignment.description}\n\n"
        f"Language: {code_submission.language or 'unknown'}\n"
        f"Max score: {code_submission.assignment.max_score}\n"
        "Return ONLY valid JSON with keys:\n"
        "syntax, logic, structure, readability, summary.\n"
        "Each score must be a number from 0 to 10.\n"
        "summary must explain major strengths, bugs, and improvements.\n\n"
        f"Student code:\n{code_submission.code}"
    )
    try:
        raw_feedback = generate_text(prompt, schema=RUBRIC_SCHEMA).strip()
    except Exception as exc:  # noqa: BLE001
        error = ai_error_payload(exc)
        raw_feedback = f"{error['title']}\n{error['message']}\nSuggestion: {error['suggestion']}"

    rubric_data = _extract_json_dict(raw_feedback)

    if not rubric_data and _is_ai_service_feedback(raw_feedback):
        code_submission.score = 0.0
        code_submission.ai_feedback = raw_feedback
        code_submission.save(update_fields=["score", "ai_feedback"])
        from teacher.services.performance import sync_code_submission_record

        sync_code_submission_record(code_submission, evaluation_type="ai")
        return code_submission

    syntax_score = _parse_rubric_score(rubric_data.get("syntax"))
    logic_score = _parse_rubric_score(rubric_data.get("logic"))
    structure_score = _parse_rubric_score(rubric_data.get("structure"))
    readability_score = _parse_rubric_score(rubric_data.get("readability"))
    summary = str(rubric_data.get("summary", "")).strip()

    # If JSON parsing fails, preserve existing behavior as fallback.
    if not rubric_data:
        score, feedback = _ai_grade(prompt, code_submission.assignment.max_score)
        code_submission.score = score
        code_submission.ai_feedback = feedback
        code_submission.save(update_fields=["score", "ai_feedback"])
        from teacher.services.performance import sync_code_submission_record

        sync_code_submission_record(code_submission, evaluation_type="ai")
        return code_submission

    if not syntax_ok:
        syntax_score = 0.0
        if summary:
            summary = f"Syntax error detected. {summary}"
        else:
            summary = "Syntax error detected."

    rubric_total = syntax_score + logic_score + structure_score + readability_score
    normalized_score = (rubric_total / 40.0) * code_submission.assignment.max_score
    final_score = round(clamp_score(normalized_score, code_submission.assignment.max_score), 2)

    feedback_parts = [
        f"Syntax: {syntax_score:.1f}/10",
        f"Logic: {logic_score:.1f}/10",
        f"Structure: {structure_score:.1f}/10",
        f"Readability: {readability_score:.1f}/10",
    ]
    if syntax_error_message:
        feedback_parts.append(f"Syntax error detail: {syntax_error_message}")
    if summary:
        feedback_parts.append(f"Summary: {summary}")

    code_submission.score = final_score
    code_submission.ai_feedback = "\n".join(feedback_parts)
    code_submission.save(update_fields=["score", "ai_feedback"])
    from teacher.services.performance import sync_code_submission_record

    sync_code_submission_record(code_submission, evaluation_type="ai")
    return code_submission


def evaluate_quiz_for_student(assignment: Assignment, student) -> QuizResult:
    questions = assignment.quiz_questions.all()
    total_questions = questions.count()
    if total_questions == 0:
        result, _ = QuizResult.objects.update_or_create(
            assignment=assignment,
            student=student,
            defaults={
                "total_questions": 0,
                "correct_answers": 0,
                "score": 0,
                "feedback": "No questions configured.",
            },
        )
        from teacher.services.performance import sync_quiz_result_record

        sync_quiz_result_record(result, evaluation_type="auto")
        return result

    answers = QuizAnswer.objects.filter(
        question__assignment=assignment,
        student=student,
    ).select_related("question")
    answer_map = {answer.question_id: answer.selected_option for answer in answers}

    correct_count = 0
    
    # Check if this is a legacy backfilled quiz where all correct answers default to 'A'
    is_legacy_backfill = all(q.correct_answer == 'A' for q in questions)
    
    if is_legacy_backfill:
        # Give automatic full credit since we don't have the original answer key
        correct_count = total_questions
    else:
        for question in questions:
            if answer_map.get(question.id) == question.correct_answer:
                correct_count += 1

    score = (correct_count / total_questions) * assignment.max_score
    feedback = f"Auto-graded quiz: {correct_count}/{total_questions} correct."
    result, _ = QuizResult.objects.update_or_create(
        assignment=assignment,
        student=student,
        defaults={
            "total_questions": total_questions,
            "correct_answers": correct_count,
            "score": round(score, 2),
            "feedback": feedback,
        },
    )
    from teacher.services.performance import sync_quiz_result_record

    sync_quiz_result_record(result, evaluation_type="auto")
    return result


def evaluate_quiz_for_assignment(assignment: Assignment) -> int:
    student_ids = QuizAnswer.objects.filter(
        question__assignment=assignment
    ).values_list("student_id", flat=True).distinct()
    graded = 0
    for student_id in student_ids:
        student = assignment.classroom.students.filter(id=student_id).first()
        if student:
            evaluate_quiz_for_student(assignment, student)
            graded += 1
    return graded


def get_student_score_records(classroom, student):
    assignments = classroom.assignments.all().order_by("due_date")
    records = []
    graded_scores = []

    for assignment in assignments:
        score = None
        feedback = ""
        submitted_at = None

        if assignment.assignment_type == Assignment.ASSIGNMENT_TYPE_FILE:
            submission = Submission.objects.filter(assignment=assignment, student=student).first()
            if submission:
                score = submission.score
                feedback = submission.ai_feedback
                submitted_at = submission.submitted_at
        elif assignment.assignment_type == Assignment.ASSIGNMENT_TYPE_CODE:
            submission = CodeSubmission.objects.filter(assignment=assignment, student=student).first()
            if submission:
                score = submission.score
                feedback = submission.ai_feedback
                submitted_at = submission.submitted_at
        else:
            if QuizAnswer.objects.filter(question__assignment=assignment, student=student).exists():
                result = evaluate_quiz_for_student(assignment, student)
                score = result.score
                feedback = result.feedback
                submitted_at = result.evaluated_at

        records.append({
            "assignment": assignment,
            "score": score,
            "feedback": feedback,
            "submitted_at": submitted_at,
        })
        if score is not None:
            graded_scores.append(float(score))

    average_score = round(sum(graded_scores) / len(graded_scores), 2) if graded_scores else 0
    return records, average_score


def get_classroom_student_performance(classroom):
    rows = []
    for student in classroom.students.all():
        records, avg_score = get_student_score_records(classroom, student)
        submission_count = len([record for record in records if record["submitted_at"] is not None])
        rows.append({
            "student": student,
            "submissions": submission_count,
            "avg_score": avg_score if submission_count else "N/A",
        })
    return rows
