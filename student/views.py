from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
import ast
from .models import StudentProfile
import json
import re
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.urls import reverse
from chat.views import RESPONSE_STYLE_INSTRUCTION, format_ai_reply
from chat.schemas import CHAT_SCHEMA
from chat.ai_service import ai_error_payload, generate_text, normalize_ai_exception
from daily_challenges.models import DailyChallengeSession, StudentPoints
from daily_challenges.services import get_today_challenge_set, refresh_challenge_set
from skill_assessment.models import StudentSkill
from .models import ChatMessage, ChatSession, ImageQuery
from .context_processors import ACTIVE_CLASSROOM_SESSION_KEY, resolve_active_student_classroom
from accounts.services import has_recent_login_2fa_otp
from .services.vision import ImageQueryError, upload_image_to_ai
from .services.chat_memory import (
    append_message,
    build_context_payload,
    cleanup_expired_sessions,
    create_chat_session,
    get_memory_settings,
    get_valid_messages,
    get_user_session_or_404,
)
from teacher.models import (
    Assignment,
    ClassRoom,
    CodeSubmission,
    LectureNote,
    PerformanceRecord,
    QuizAnswer,
    QuizQuestion,
    QuizResult,
    Submission,
)
from teacher.services.evaluation import evaluate_quiz_for_student
from teacher.services.performance import (
    get_student_performance_summary,
    sync_code_submission_record,
    sync_file_submission_record,
)
from .upload_validation import validate_assignment_upload, validate_profile_image
from teacher.services.course_readme import render_course_readme_html
from kodehax_academy.mobile import render_for_device


CODE_FENCE_PATTERN = re.compile(r"```[\w+-]*\n[\s\S]*?\n```")
JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", re.IGNORECASE)

STRUCTURED_RESPONSE_TEMPLATE = {
    "type": "explanation",
    "title": "",
    "content": "",
    "examples": [],
    "quiz": [],
    "follow_up": [],
    "difficulty": "easy",
    "tags": [],
}

def build_system_prompt(mode):
    prompts = {
        "tutor": "You are a personalized AI tutor for students. Teach clearly, adapt difficulty, and guide the next learning step.",
        "quiz": "You are a quiz engine that generates adaptive, non-repetitive practice questions in multiple difficulty levels.",
        "summarize": "You are a lesson summarizer that creates revision-friendly notes, key points, and quick recap material.",
        "course_qa": "You are a course assistant. Answer course-related questions with context awareness and personalized guidance.",
    }
    strict_mode_rules = {
        "tutor": (
            "STRICT MODE: Act only as AI Tutor. Teach the concept, explain it, guide the student, and optionally include examples or code.\n"
            "Do not switch into quiz-only or summarize-only behavior unless it directly supports teaching."
        ),
        "course_qa": (
            "STRICT MODE: Act only as Course Q&A. Answer questions related to the student's course, syllabus, lesson, or academic topic.\n"
            "If the request is unrelated to course learning, politely redirect the student back to course-focused questions."
        ),
        "quiz": (
            "STRICT MODE: Act only as Quiz Me. Always return quiz-style practice content.\n"
            "Do not give a plain explanatory answer instead of a quiz. Generate practice questions even if the user asks for explanation."
        ),
        "summarize": (
            "STRICT MODE: Act only as Summarize. Always produce a summary, revision notes, or condensed explanation.\n"
            "Do not switch into quiz-generation or open-ended tutoring unless it is included as a short add-on after the summary."
        ),
    }
    return (
        f"{prompts.get(mode, prompts['tutor'])}\n\n"
        "You are integrated into Kodehax Academy. Preserve the current product behavior while improving it.\n"
        "Never act like a generic chatbot.\n"
        f"{strict_mode_rules.get(mode, strict_mode_rules['tutor'])}\n"
        "The selected tab is authoritative and must control the behavior of the response.\n"
        "Always adapt using student level, current topic, prior mistakes, and performance context when available.\n"
        "Keep answers crisp, sharp, and high-signal by default.\n"
        "If the student struggles, simplify and teach step by step. If the student succeeds, raise difficulty slightly.\n"
        "When code is involved, include clean code, an explanation, and time/space complexity.\n"
        "When math or formulas help, write them using standard LaTeX delimiters such as $...$ or $$...$$.\n"
        "When debugging or reviewing incorrect work, identify whether the issue is conceptual, syntax, or logical.\n"
        "When summarizing, include key points, revision bullets, and formulas if relevant.\n"
        "When quizzing, provide varied questions across easy, medium, and hard levels.\n"
        "Avoid repeating the same examples or questions from the recent conversation.\n\n"
        f"{RESPONSE_STYLE_INSTRUCTION}"
    )


def _safe_json_load(text):
    if not text:
        return {}
    raw = text.strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    block_match = JSON_BLOCK_PATTERN.search(raw)
    if block_match:
        try:
            parsed = json.loads(block_match.group(1))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(raw[start : end + 1])
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        candidate = raw[start : end + 1]
        candidate = re.sub(r"\btrue\b", "True", candidate)
        candidate = re.sub(r"\bfalse\b", "False", candidate)
        candidate = re.sub(r"\bnull\b", "None", candidate)
        try:
            parsed = ast.literal_eval(candidate)
            return parsed if isinstance(parsed, dict) else {}
        except (SyntaxError, ValueError):
            return {}


def _coerce_string_list(values, limit=None):
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True)
        text = text.strip()
        if text:
            result.append(text)
    if limit is not None:
        return result[:limit]
    return result


def _coerce_quiz_list(values):
    if not isinstance(values, list):
        return []
    quiz_items = []
    for item in values:
        if not isinstance(item, dict):
            continue
        options = item.get("options", [])
        if isinstance(options, dict):
            options = [f"{key}) {value}" for key, value in options.items()]
        options = _coerce_string_list(options, limit=6)
        quiz_items.append({
            "level": str(item.get("level", "easy")).strip().lower() or "easy",
            "question": str(item.get("question", "")).strip(),
            "options": options,
            "answer": str(item.get("answer", "")).strip(),
            "explanation": str(item.get("explanation", "")).strip(),
        })
    return [item for item in quiz_items if item["question"]][:9]


def _normalize_structured_response(payload, mode):
    data = STRUCTURED_RESPONSE_TEMPLATE.copy()
    if isinstance(payload, dict):
        data["type"] = str(payload.get("type", "")).strip().lower() or data["type"]
        data["title"] = str(payload.get("title", "")).strip()
        data["content"] = str(payload.get("content", "")).strip()
        data["examples"] = _coerce_string_list(payload.get("examples", []), limit=6)
        data["quiz"] = _coerce_quiz_list(payload.get("quiz", []))
        data["follow_up"] = _coerce_string_list(payload.get("follow_up", []), limit=6)
        data["difficulty"] = str(payload.get("difficulty", "")).strip().lower() or data["difficulty"]
        data["tags"] = _coerce_string_list(payload.get("tags", []), limit=8)

    mode_default_type = {
        "tutor": "explanation",
        "course_qa": "analysis",
        "quiz": "quiz",
        "summarize": "explanation",
    }
    if data["type"] not in {"explanation", "quiz", "analysis", "suggestion"}:
        data["type"] = mode_default_type.get(mode, "explanation")
    if mode == "quiz":
        data["type"] = "quiz"
    elif mode == "course_qa" and data["type"] == "quiz":
        data["type"] = "analysis"
    if data["difficulty"] not in {"easy", "medium", "hard"}:
        data["difficulty"] = "medium"
    if not data["title"]:
        default_titles = {
            "tutor": "Learning Guide",
            "quiz": "Adaptive Quiz Practice",
            "summarize": "Quick Summary",
            "course_qa": "Course Help",
        }
        data["title"] = default_titles.get(mode, "Assistant Response")
    if not data["follow_up"]:
        follow_up_defaults = {
            "tutor": [
                "Want a simpler explanation?",
                "See a worked example",
                "Practice this concept",
            ],
            "course_qa": [
                "Ask about another lesson topic",
                "Check prerequisites for this concept",
                "Review a related course question",
            ],
            "quiz": [
                "Try another quiz on this topic",
                "Increase the difficulty",
                "Focus on weak areas",
            ],
            "summarize": [
                "Turn this into revision notes",
                "Make it even shorter",
                "Highlight key formulas",
            ],
        }
        data["follow_up"] = follow_up_defaults.get(mode, [
            "Try a quiz on this topic",
            "Want a simpler explanation?",
            "See a real-world example",
        ])
    return data


def _structured_to_markdown(data):
    lines = [f"## {data['title']}"]
    if data["content"]:
        lines.extend(["", data["content"]])

    if data["examples"]:
        lines.extend(["", "### Examples"])
        lines.extend([f"- {item}" for item in data["examples"]])

    if data["quiz"]:
        lines.extend(["", "### Quiz"])
        for item in data["quiz"]:
            lines.append(f"- **{item['level'].title()}**: {item['question']}")
            for option in item["options"]:
                lines.append(f"  {option}")
            if item["explanation"]:
                lines.append(f"  Explanation: {item['explanation']}")

    if data["follow_up"]:
        lines.extend(["", "### Next Steps"])
        lines.extend([f"- {item}" for item in data["follow_up"]])

    if data["tags"]:
        lines.extend(["", f"Tags: {', '.join(data['tags'])}"])

    return "\n".join(lines).strip()


def _vision_response_to_chat_payload(payload):
    vision_type = payload.get("type", "notes")
    title_map = {
        "code": "Code Analysis",
        "math": "Math Explanation",
        "exam": "Exam Solution",
        "diagram": "Diagram Explanation",
        "notes": "Notes Summary",
    }
    explanation = payload.get("explanation", "").strip()
    solution = payload.get("solution", "").strip()
    content_parts = []
    if explanation:
        content_parts.append(explanation)
    if solution:
        content_parts.extend(["", "### Solution", solution])

    structured = {
        "type": "analysis" if vision_type in {"code", "exam", "diagram"} else "explanation",
        "title": title_map.get(vision_type, "Image Analysis"),
        "content": "\n".join(content_parts).strip(),
        "examples": [],
        "quiz": [],
        "follow_up": payload.get("follow_up", []),
        "difficulty": "medium",
        "tags": [vision_type, "image-analysis"],
    }
    if payload.get("steps"):
        structured["examples"] = payload["steps"]
    if payload.get("mistakes"):
        structured["examples"] = structured["examples"] + [f"Mistake: {item}" for item in payload["mistakes"]]
    return structured


def _infer_topic_from_message(user_message):
    lowered = (user_message or "").lower()
    topic_keywords = [
        "array", "arrays", "string", "strings", "loop", "loops", "recursion",
        "sorting", "search", "math", "conditionals", "debugging", "python",
    ]
    for keyword in topic_keywords:
        if keyword in lowered:
            return keyword
    return "general"


def _student_context_payload(student, user_message, mode):
    if not getattr(student, "is_authenticated", False):
        return {
            "student_level": "Intermediate",
            "preferred_difficulty": "medium",
            "current_topic_hint": _infer_topic_from_message(user_message),
            "current_mode": mode,
            "weak_topics": [],
            "strong_topics": [],
            "medium_topics": [],
            "recent_average_score": 0,
            "recent_completion_rate": 0,
            "recent_on_time_rate": 0,
            "repeated_struggle": False,
            "recent_assignments": [],
            "current_classes": [],
        }

    skill_profile = StudentSkill.objects.filter(student=student).first()
    performance = get_student_performance_summary(student)
    recent_records = (
        PerformanceRecord.objects.filter(student=student)
        .exclude(score__isnull=True)
        .order_by("-submitted_at", "-recorded_at")[:5]
    )
    current_classes = list(
        ClassRoom.objects.filter(students=student).values_list("name", flat=True)[:3]
    )

    weak_topics = []
    strong_topics = []
    medium_topics = []
    if skill_profile:
        weak_topics = list((skill_profile.weak_topics or {}).keys())[:5]
        strong_topics = [str(item) for item in (skill_profile.strong_topics or [])[:5]]
        medium_topics = [
            str(item)
            for item in (skill_profile.assessment_snapshot or {}).get("medium_topics", [])[:5]
        ]

    recent_scores = [round(float(record.score), 2) for record in recent_records if record.score is not None]
    average_recent_score = round(sum(recent_scores) / len(recent_scores), 2) if recent_scores else 0
    repeated_struggle = bool(recent_scores) and average_recent_score < 50

    preferred_difficulty = "medium"
    student_level = "Intermediate"
    if skill_profile and skill_profile.skill_level:
        student_level = skill_profile.skill_level
    elif performance["summary"]["average_score"] >= 75:
        student_level = "Advanced"
    elif performance["summary"]["average_score"] <= 40:
        student_level = "Beginner"

    normalized_level = student_level.lower()
    if "beginner" in normalized_level or "basic" in normalized_level:
        preferred_difficulty = "easy"
    elif "advanced" in normalized_level or "expert" in normalized_level:
        preferred_difficulty = "hard"

    return {
        "student_level": student_level,
        "preferred_difficulty": preferred_difficulty,
        "current_topic_hint": _infer_topic_from_message(user_message),
        "current_mode": mode,
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
        "medium_topics": medium_topics,
        "recent_average_score": performance["summary"]["average_score"],
        "recent_completion_rate": performance["summary"]["completion_percentage"],
        "recent_on_time_rate": performance["summary"]["on_time_submission_rate"],
        "repeated_struggle": repeated_struggle,
        "recent_assignments": [record.assignment_title for record in recent_records if record.assignment_title][:5],
        "current_classes": current_classes,
    }


def _session_payload(session):
    messages = list(session.messages.order_by("-created_at", "-id")[:1])
    latest_message = messages[0] if messages else None
    preview = ""
    if latest_message:
        preview = (latest_message.content or "").strip()
        if preview.startswith("## "):
            preview = preview.splitlines()[0].replace("##", "").strip()
        elif preview.startswith("{") and '"title"' in preview:
            try:
                parsed = _safe_json_load(preview)
                preview = parsed.get("title") or parsed.get("content") or preview
            except Exception:
                pass
        preview = preview.replace("\n", " ")[:90].strip()
    return {
        "id": session.id,
        "title": session.title or "New Chat",
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "expires_at": session.expires_at.isoformat() if session.expires_at else None,
        "is_active": session.is_active,
        "is_expired": session.is_expired,
        "last_message_preview": preview,
        "last_message_role": latest_message.role if latest_message else "",
    }


def _message_payload(message):
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


def _build_ai_prompt(mode, history, user_message, student_context, memory_context=None):
    transcript_lines = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "user")).strip().lower()
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        if role not in {"user", "assistant"}:
            role = "user"
        transcript_lines.append(f"{role.title()}: {content}")

    transcript = "\n".join(transcript_lines) if transcript_lines else "No prior conversation."
    history_examples = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "user")).strip().lower()
        content = str(item.get("content", "")).strip()
        if role == "assistant" and content:
            history_examples.append(content[:240])

    recent_response_patterns = history_examples[-3:] if history_examples else []
    mode_requirements = {
        "tutor": "Prioritize explanation, examples, and targeted next steps.",
        "course_qa": "Keep answers course-focused and add clarification prompts when context is missing.",
        "quiz": "Return exactly three quiz items: easy, medium, and hard. Avoid duplicate concepts.",
        "summarize": "Include key points, bullet-style revision notes, and formulas if relevant.",
    }
    direct_intent = {
        "tutor": "Primary objective: teach the student's requested topic as a tutor.",
        "course_qa": "Primary objective: answer the student's question strictly as course-related Q&A.",
        "quiz": "Primary objective: convert the student's topic into quiz-style practice content.",
        "summarize": "Primary objective: summarize the student's provided topic or request into compact study material.",
    }
    return (
        f"{build_system_prompt(mode)}\n\n"
        "Return a single valid JSON object only. No markdown wrapper. No prose outside JSON.\n"
        "The JSON schema is:\n"
        "{\n"
        '  "type": "explanation | quiz | analysis | suggestion",\n'
        '  "title": "Short heading",\n'
        '  "content": "Main explanation",\n'
        '  "examples": ["..."],\n'
        '  "quiz": [\n'
        '    {"level": "easy | medium | hard", "question": "...", "options": ["..."], "answer": "...", "explanation": "..."}\n'
        "  ],\n"
        '  "follow_up": ["..."],\n'
        '  "difficulty": "easy | medium | hard",\n'
        '  "tags": ["..."]\n'
        "}\n\n"
        "Rules:\n"
        "- Always fill every top-level field.\n"
        f"- {direct_intent.get(mode, direct_intent['tutor'])}\n"
        "- follow_up must contain 3 to 4 short actionable suggestions.\n"
        "- If code is needed, include it inside content using fenced code blocks.\n"
        "- Prefer concise, high-signal wording over long filler.\n"
        "- Keep most answers compact unless the question clearly needs depth.\n"
        "- Start with the direct answer before extra detail.\n"
        "- If analyzing mistakes, classify them as conceptual, syntax, or logical and explain why.\n"
        "- If the user seems to be struggling, simplify and break the idea into smaller steps.\n"
        "- If performance suggests strong understanding, increase challenge slightly.\n"
        "- Keep output modular so the UI can render sections.\n"
        "- If the topic is mathematical, include LaTeX only where it improves clarity.\n"
        f"- Mode requirement: {mode_requirements.get(mode, mode_requirements['tutor'])}\n"
        "- Do not blend behaviors across tabs unless it is a very small supporting addition.\n\n"
        "Student context:\n"
        f"{json.dumps(student_context, ensure_ascii=True)}\n\n"
        "Session memory context:\n"
        f"{json.dumps(memory_context or {}, ensure_ascii=True)}\n\n"
        "Conversation so far:\n"
        f"{transcript}\n\n"
        "Recent assistant response patterns to avoid repeating too closely:\n"
        f"{json.dumps(recent_response_patterns, ensure_ascii=True)}\n\n"
        "Latest user message:\n"
        f"User: {user_message}\n\n"
        "Reply as the assistant."
    )


def _run_text_chat(user, user_message, mode, history, memory_context=None):
    student_context = _student_context_payload(user, user_message, mode)
    prompt = _build_ai_prompt(mode, history, user_message, student_context, memory_context=memory_context)
    raw_response = generate_text(
        prompt,
        schema=CHAT_SCHEMA,
    )
    parsed = _safe_json_load(raw_response)
    if not parsed:
        parsed = {
            "type": "quiz" if mode == "quiz" else "explanation",
            "title": "Assistant Response",
            "content": raw_response.strip(),
            "examples": [],
            "quiz": [],
            "follow_up": [
                "Try a quiz on this topic",
                "Want a simpler explanation?",
                "See a real-world example",
            ],
            "difficulty": student_context["preferred_difficulty"],
            "tags": [mode, student_context["current_topic_hint"]],
        }
    structured = _normalize_structured_response(parsed, mode)
    reply = format_ai_reply(_structured_to_markdown(structured))
    if not reply or not structured["content"]:
        raise ValueError("Groq returned an empty response.")
    return {
        "reply": reply,
        "has_code": bool(CODE_FENCE_PATTERN.search(reply)),
        "structured": structured,
        "context": {
            "student_level": student_context["student_level"],
            "difficulty": structured["difficulty"],
            "weak_topics": student_context["weak_topics"],
        },
    }

@login_required
@require_POST
def llama_chat(request):
    try:
        body = json.loads(request.body)
        user_message = body.get("message", "")
        mode = body.get("mode", "tutor")
        history = body.get("history", [])
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not user_message:
        return JsonResponse({"error": "Message is required"}, status=400)

    try:
        return JsonResponse(_run_text_chat(request.user, user_message, mode, history))
    except Exception as e:
        error = normalize_ai_exception(e)
        return JsonResponse({"error": error.message, "ai_error": ai_error_payload(error)}, status=error.status_code)

def chat_page(request):
    cleanup_expired_sessions(delete=False)
    return render_for_device(request, 'student/chat.html', {
        "memory_settings": get_memory_settings(),
    })


@login_required
@require_POST
def image_query_api(request):
    uploaded_image = request.FILES.get("image")
    session_id = request.POST.get("session_id")
    if not uploaded_image:
        return JsonResponse(
            {"error": "No image was uploaded.", "suggestion": "Upload a JPG or PNG image."},
            status=400,
        )

    try:
        ai_payload = upload_image_to_ai(uploaded_image)
    except ImageQueryError as exc:
        return JsonResponse({"error": exc.message, "suggestion": exc.suggestion}, status=400)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse(
            {"error": f"Unexpected error: {type(exc).__name__}", "suggestion": "Try a clearer image."},
            status=500,
        )

    session = None
    if session_id:
        try:
            session = get_user_session_or_404(request.user, session_id)
        except ChatSession.DoesNotExist:
            return JsonResponse({"error": "Session not found.", "suggestion": "Start a new chat and try again."}, status=404)

    image_query = ImageQuery.objects.create(
        user=request.user,
        image=uploaded_image,
        extracted_text=ai_payload.get("detected_content", ""),
        ai_response=ai_payload,
    )
    structured = _vision_response_to_chat_payload(ai_payload)
    reply = format_ai_reply(_structured_to_markdown(structured))
    if session:
        append_message(session, ChatMessage.ROLE_USER, f"[Uploaded image] {uploaded_image.name}")
        append_message(session, ChatMessage.ROLE_ASSISTANT, reply)
    return JsonResponse(
        {
            "reply": reply,
            "has_code": bool(CODE_FENCE_PATTERN.search(reply)),
            "structured": structured,
            "session": _session_payload(session) if session else None,
            "image_query": {
                "id": image_query.id,
                "image_url": image_query.image.url,
                "created_at": image_query.created_at.isoformat(),
                "detected_content": ai_payload.get("detected_content", ""),
                "raw": ai_payload,
            },
        },
        status=201,
    )


@login_required
@require_POST
def chat_start_api(request):
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        body = {}
    first_message = str(body.get("message", "")).strip()
    session = create_chat_session(request.user, first_message=first_message)
    if first_message:
        append_message(session, ChatMessage.ROLE_USER, first_message)
    return JsonResponse({
        "session": _session_payload(session),
        "memory": get_memory_settings(),
    }, status=201)


@login_required
def chat_sessions_api(request):
    if request.method != "GET":
        return JsonResponse({"error": "GET method required"}, status=405)

    cleanup_expired_sessions(delete=False)
    page_number = request.GET.get("page", "1")
    page_obj = Paginator(
        ChatSession.objects.filter(
            user=request.user,
            is_active=True,
            expires_at__gt=timezone.now(),
        ).order_by("-updated_at"),
        20,
    ).get_page(page_number)
    return JsonResponse({
        "sessions": [_session_payload(session) for session in page_obj.object_list],
        "pagination": {
            "page": page_obj.number,
            "pages": page_obj.paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
        "memory": get_memory_settings(),
    })


@login_required
def chat_session_detail_api(request, session_id):
    try:
        session = get_user_session_or_404(request.user, session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Session not found."}, status=404)

    if request.method == "GET":
        valid_messages = get_valid_messages(session)
        return JsonResponse({
            "session": _session_payload(session),
            "messages": [_message_payload(message) for message in valid_messages],
            "memory": get_memory_settings(),
        })

    if request.method == "DELETE":
        session.is_active = False
        session.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"success": True})

    return JsonResponse({"error": "Unsupported method."}, status=405)


@login_required
@require_POST
def chat_session_message_api(request, session_id):
    try:
        session = get_user_session_or_404(request.user, session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Session not found."}, status=404)

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    user_message = str(body.get("message", "")).strip()
    mode = body.get("mode", "tutor")
    if not user_message:
        return JsonResponse({"error": "Message is required"}, status=400)

    valid_messages = list(get_valid_messages(session))
    history = [{"role": item.role, "content": item.content} for item in valid_messages]
    memory_context = build_context_payload(
        session,
        _student_context_payload(request.user, user_message, mode),
    )

    if not session.title:
        session.title = user_message[:255]
        session.save(update_fields=["title", "updated_at"])

    append_message(session, ChatMessage.ROLE_USER, user_message)

    try:
        ai_payload = _run_text_chat(
            request.user,
            user_message,
            mode,
            history,
            memory_context=memory_context,
        )
    except Exception as exc:
        error = normalize_ai_exception(exc)
        return JsonResponse({"error": error.message, "ai_error": ai_error_payload(error)}, status=error.status_code)

    assistant_message = append_message(session, ChatMessage.ROLE_ASSISTANT, ai_payload["reply"])
    return JsonResponse({
        **ai_payload,
        "session": _session_payload(session),
        "message": _message_payload(assistant_message),
        "memory": get_memory_settings(),
    })


@login_required
@require_POST
def chat_session_rename_api(request, session_id):
    try:
        session = get_user_session_or_404(request.user, session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Session not found."}, status=404)

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    new_title = str(body.get("title", "")).strip()
    if not new_title:
        return JsonResponse({"error": "Title is required."}, status=400)
    session.title = new_title[:255]
    session.save(update_fields=["title", "updated_at"])
    return JsonResponse({"session": _session_payload(session)})


@login_required
@require_POST
def chat_session_clear_api(request, session_id):
    try:
        session = get_user_session_or_404(request.user, session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Session not found."}, status=404)

    session.messages.all().delete()
    session.updated_at = timezone.now()
    session.save(update_fields=["updated_at"])
    return JsonResponse({"success": True, "session": _session_payload(session)})


def _ensure_student(request):
    if request.user.role != "student":
        messages.error(
            request,
            "Student portal access denied for current session. Use a separate browser profile/incognito for parallel logins."
        )
        return redirect("home")
    return None


def _build_assignment_rows(assignments, student):
    assignment_list = list(assignments)
    assignment_ids = [assignment.id for assignment in assignment_list]
    now = timezone.now()

    file_submissions = Submission.objects.filter(
        student=student,
        assignment_id__in=assignment_ids
    ).select_related("assignment")
    file_submission_map = {
        submission.assignment_id: submission for submission in file_submissions
    }

    code_submissions = CodeSubmission.objects.filter(
        student=student,
        assignment_id__in=assignment_ids
    ).select_related("assignment")
    code_submission_map = {
        submission.assignment_id: submission for submission in code_submissions
    }

    quiz_result_map = {
        result.assignment_id: result
        for result in QuizResult.objects.filter(
            student=student,
            assignment_id__in=assignment_ids
        )
    }
    quiz_attempted_ids = set(
        QuizAnswer.objects.filter(
            student=student,
            question__assignment_id__in=assignment_ids
        ).values_list("question__assignment_id", flat=True).distinct()
    )

    rows = []
    for assignment in assignment_list:
        is_archived = assignment.due_date < now
        row = {
            "assignment": assignment,
            "status_label": "Archived" if is_archived else "Pending",
            "status_class": "amber",
            "action_label": "View Assignment" if is_archived else "Open",
            "can_submit": not is_archived,
            "is_archived": is_archived,
        }

        if assignment.assignment_type == Assignment.ASSIGNMENT_TYPE_FILE:
            row["submission"] = file_submission_map.get(assignment.id)
            row["action_label"] = "View Assignment" if is_archived else "Submit"
            if row["submission"]:
                row["status_label"] = "Archived" if is_archived else "Submitted"
                row["status_class"] = "amber" if is_archived else "emerald"
                if not is_archived and assignment.allows_multiple_attempts:
                    row["action_label"] = "Re-submit"
                else:
                    row["action_label"] = "View Submission"
        elif assignment.assignment_type == Assignment.ASSIGNMENT_TYPE_CODE:
            row["submission"] = code_submission_map.get(assignment.id)
            row["action_label"] = "View Assignment" if is_archived else "Write Code"
            if row["submission"]:
                row["status_label"] = "Archived" if is_archived else "Submitted"
                row["status_class"] = "amber" if is_archived else "emerald"
                if not is_archived and assignment.allows_multiple_attempts:
                    row["action_label"] = "Update Code"
                else:
                    row["action_label"] = "View Submission"
        else:
            row["submission"] = quiz_result_map.get(assignment.id)
            row["action_label"] = "View Assignment" if is_archived else "Take Assignment"
            attempted = row["submission"] or assignment.id in quiz_attempted_ids
            if attempted:
                row["status_class"] = "amber" if is_archived else "emerald"
                if is_archived:
                    row["status_label"] = "Archived"
                    row["action_label"] = "Review Answers"
                elif assignment.allows_multiple_attempts:
                    row["status_label"] = "Attempted"
                    row["action_label"] = "Retake Assignment"
                else:
                    row["status_label"] = "Completed"
                    row["action_label"] = "View Assignment"
        rows.append(row)
    return rows


def _parse_quiz_questions_from_description(raw_text):
    if not raw_text:
        return []
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    questions = []
    current = None
    question_pattern = re.compile(r"^Q\s*\d+\s*[)\.:]?\s*(.+)$", re.IGNORECASE)
    option_pattern = re.compile(r"^([ABCD])[)\.:]\s*(.+)$", re.IGNORECASE)

    def finalize_current():
        if current and all(current.get(opt) for opt in ("A", "B", "C", "D")):
            questions.append(current.copy())

    for line in lines:
        q_match = question_pattern.match(line)
        if q_match:
            finalize_current()
            current = {
                "question": q_match.group(1).strip(),
                "A": "",
                "B": "",
                "C": "",
                "D": "",
            }
            continue

        if not current:
            continue

        o_match = option_pattern.match(line)
        if o_match:
            current[o_match.group(1).upper()] = o_match.group(2).strip()
            continue

        if not any(current.get(opt) for opt in ("A", "B", "C", "D")):
            current["question"] = f"{current['question']} {line}".strip()

    finalize_current()
    return questions

@login_required
def student_dashboard(request):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    skill_profile = StudentSkill.objects.filter(student=request.user).first()
    if not skill_profile:
        return redirect("skill_assessment_entry")

    profile, _ = StudentProfile.objects.get_or_create(user=request.user)

    # Ensure weak_topics is always a dict, never None or a list
    if not isinstance(skill_profile.weak_topics, dict):
        skill_profile.weak_topics = {}
    
    # Ensure strong_topics is always a list
    if not isinstance(skill_profile.strong_topics, list):
        skill_profile.strong_topics = []

    joined_classes = ClassRoom.objects.filter(
        students=request.user
    ).select_related("teacher").prefetch_related("assignments").order_by("-created_at")

    daily_challenge_set = get_today_challenge_set(request.user)
    refresh_challenge_set(daily_challenge_set)
    daily_challenge_set.refresh_from_db()
    solved_daily_count = daily_challenge_set.challenges.filter(status="solved").count()
    total_daily_count = daily_challenge_set.challenges.count()
    student_points, _ = StudentPoints.objects.get_or_create(student=request.user)
    current_session = DailyChallengeSession.objects.filter(
        student=request.user,
        date=daily_challenge_set.date,
    ).first()

    assignments = Assignment.objects.filter(
        classroom__students=request.user,
        due_date__gte=timezone.now(),
    ).select_related("classroom")
    assignment_rows = _build_assignment_rows(assignments, request.user)
    submission_map = {row["assignment"].id: row for row in assignment_rows}
    personal_notes = LectureNote.objects.filter(
        classroom__students=request.user,
    ).select_related("classroom", "teacher")[:4]

    return render_for_device(request, "student/dashboard.html", {
        "profile": profile,
        "joined_classes": joined_classes,
        "submission_map": submission_map,
        "personal_notes": personal_notes,
        "skill_profile": skill_profile,
        "medium_topics": skill_profile.assessment_snapshot.get("medium_topics", []),
        "daily_challenge_set": daily_challenge_set,
        "solved_daily_count": solved_daily_count,
        "total_daily_count": total_daily_count,
        "student_points": student_points,
        "current_session": current_session,
    })

@login_required
def join_classroom(request):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    if request.method == "POST":
        class_code = request.POST.get("class_code", "").strip().upper()
        if not class_code:
            messages.error(request, "Please enter a class code.")
            return redirect("student_dashboard")

        classroom = ClassRoom.objects.filter(
            class_code=class_code,
            is_active=True
        ).first()

        if not classroom:
            messages.error(request, "Invalid or inactive class code.")
            return redirect("student_dashboard")

        classroom.students.add(request.user)
        request.session[ACTIVE_CLASSROOM_SESSION_KEY] = classroom.id
        messages.success(
            request,
            f"You joined {classroom.name}."
        )
    return redirect("student_dashboard")

@login_required
def class_detail(request, class_id):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    classroom = get_object_or_404(
        ClassRoom.objects.select_related("teacher"),
        id=class_id,
        students=request.user
    )

    now = timezone.now()
    active_assignments = classroom.assignments.filter(
        due_date__gte=now
    ).order_by("due_date")
    archived_assignments = classroom.assignments.filter(
        due_date__lt=now
    ).order_by("-due_date")
    selected_note_id = request.GET.get("note")
    lecture_notes = classroom.lecture_notes.select_related("teacher")
    selected_note = None
    if selected_note_id:
        selected_note = lecture_notes.filter(id=selected_note_id).first()
        lecture_notes = lecture_notes.filter(id=selected_note_id) if selected_note else lecture_notes[:10]
    else:
        lecture_notes = lecture_notes[:10]

    return render_for_device(request, "student/class_detail.html", {
        "classroom": classroom,
        "active_assignment_rows": _build_assignment_rows(active_assignments, request.user),
        "archived_assignment_rows": _build_assignment_rows(archived_assignments, request.user),
        "lecture_notes": lecture_notes,
        "selected_note": selected_note,
        "classroom_readme_html": render_course_readme_html(classroom.readme_content),
        "has_classroom_readme": bool((classroom.readme_content or "").strip()),
    })


@login_required
def view_assignments(request):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    joined_classrooms = ClassRoom.objects.filter(students=request.user).order_by("name", "id")
    active_classroom = resolve_active_student_classroom(request, joined_classrooms)
    active_assignments = Assignment.objects.filter(
        classroom__students=request.user,
        due_date__gte=timezone.now(),
    ).select_related("classroom", "classroom__teacher").order_by("due_date")
    archived_assignments = Assignment.objects.filter(
        classroom__students=request.user,
        due_date__lt=timezone.now(),
    ).select_related("classroom", "classroom__teacher").order_by("-due_date")
    if active_classroom:
        active_assignments = active_assignments.filter(classroom=active_classroom)
        archived_assignments = archived_assignments.filter(classroom=active_classroom)

    active_assignment_rows = _build_assignment_rows(active_assignments, request.user)
    archived_assignment_rows = _build_assignment_rows(archived_assignments, request.user)

    return render_for_device(request, "student/assignment/view_assignment.html", {
        "active_assignment_rows": active_assignment_rows,
        "archived_assignment_rows": archived_assignment_rows,
        "active_classroom": active_classroom,
    })


@login_required
def student_performance_dashboard(request):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    analytics = get_student_performance_summary(request.user)
    summary = analytics["summary"]
    charts = analytics["charts"]
    upcoming_assignments = Assignment.objects.filter(
        classroom__students=request.user,
        due_date__gte=timezone.now(),
    ).select_related("classroom").order_by("due_date")[:8]
    recent_results = PerformanceRecord.objects.filter(
        student=request.user
    ).exclude(score__isnull=True).order_by("-submitted_at", "-recorded_at")[:8]
    notifications = []
    for assignment in upcoming_assignments:
        if assignment.assignment_type == Assignment.ASSIGNMENT_TYPE_QUIZ:
            assignment_url = reverse("take_quiz_assignment", kwargs={"assignment_id": assignment.id})
        elif assignment.assignment_type == Assignment.ASSIGNMENT_TYPE_CODE:
            assignment_url = reverse("submit_code_assignment", kwargs={"assignment_id": assignment.id})
        else:
            assignment_url = reverse("submit_assignment", kwargs={"assignment_id": assignment.id})
        notifications.append(
            {
                "title": f"Due soon: {assignment.title}",
                "body": f"{assignment.classroom.name} • {assignment.due_date:%b %d, %I:%M %p}",
                "time": assignment.due_date,
                "kind": "due",
                "url": assignment_url,
            }
        )
    for result in recent_results:
        notifications.append(
            {
                "title": f"Scored {result.score:.0f}% in {result.assignment_title}",
                "body": "Submission evaluated and added to your performance history.",
                "time": result.recorded_at or result.submitted_at,
                "kind": "result",
                "url": None,
            }
        )
    notifications.sort(key=lambda item: item["time"] or timezone.now(), reverse=True)

    return render_for_device(request, "student/performance.html", {
        "summary": summary,
        "records": analytics["records"],
        "score_progression_labels": charts["score_progression_labels"],
        "score_progression_values": charts["score_progression_values"],
        "assignment_score_labels": charts["assignment_score_labels"],
        "assignment_score_values": charts["assignment_score_values"],
        "submission_trend_labels": charts["submission_trend_labels"],
        "submission_trend_values": charts["submission_trend_values"],
        "notifications": notifications[:20],
    })


@login_required
def submit_assignment(request, assignment_id):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    assignment = get_object_or_404(
        Assignment.objects.select_related("classroom", "classroom__teacher"),
        id=assignment_id,
        classroom__students=request.user
    )

    if assignment.assignment_type == Assignment.ASSIGNMENT_TYPE_QUIZ:
        return redirect("take_quiz_assignment", assignment_id=assignment.id)
    if assignment.assignment_type == Assignment.ASSIGNMENT_TYPE_CODE:
        return redirect("submit_code_assignment", assignment_id=assignment.id)

    is_archived = assignment.due_date < timezone.now()
    existing_submission = Submission.objects.filter(
        assignment=assignment,
        student=request.user
    ).first()
    can_submit = (not is_archived) and (assignment.allows_multiple_attempts or not existing_submission)

    if request.method == "POST":
        if is_archived:
            messages.error(request, "This assignment is archived. New submissions are closed.")
            return redirect("submit_assignment", assignment_id=assignment.id)
        if not can_submit:
            messages.error(request, "This assignment allows only one attempt.")
            return redirect("submit_assignment", assignment_id=assignment.id)

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            messages.error(request, "Please select a file to submit.")
            return redirect("submit_assignment", assignment_id=assignment.id)
        try:
            validate_assignment_upload(uploaded_file)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("submit_assignment", assignment_id=assignment.id)

        if existing_submission:
            existing_submission.file = uploaded_file
            existing_submission.save(update_fields=["file"])
            sync_file_submission_record(existing_submission, evaluation_type="manual")
            success_message = "Assignment re-submitted successfully."
        else:
            submission = Submission.objects.create(
                assignment=assignment,
                student=request.user,
                file=uploaded_file,
            )
            sync_file_submission_record(submission, evaluation_type="manual")
            success_message = "Assignment submitted successfully."

        messages.success(request, success_message)
        return redirect("view_assignments")

    return render_for_device(request, "student/assignment/submit_assignment.html", {
        "assignment": assignment,
        "existing_submission": existing_submission,
        "can_submit": can_submit,
        "is_archived": is_archived,
    })


@login_required
def take_quiz_assignment(request, assignment_id):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    assignment = get_object_or_404(
        Assignment.objects.select_related("classroom"),
        id=assignment_id,
        classroom__students=request.user,
        assignment_type=Assignment.ASSIGNMENT_TYPE_QUIZ
    )
    questions = assignment.quiz_questions.all()
    if not questions.exists():
        # Backfill parser for old AI quizzes that were saved only as description text.
        parsed = _parse_quiz_questions_from_description(assignment.description)
        for item in parsed:
            QuizQuestion.objects.create(
                assignment=assignment,
                question=item["question"],
                option_a=item["A"],
                option_b=item["B"],
                option_c=item["C"],
                option_d=item["D"],
                # Old descriptions often miss answer keys; keep a placeholder.
                correct_answer="A",
            )
        questions = assignment.quiz_questions.all()

    existing_answers = {
        answer.question_id: answer.selected_option
        for answer in QuizAnswer.objects.filter(
            question__assignment=assignment,
            student=request.user,
        )
    }
    has_existing_result = QuizResult.objects.filter(
        assignment=assignment,
        student=request.user,
    ).exists()
    has_existing_attempt = bool(existing_answers) or has_existing_result
    is_archived = assignment.due_date < timezone.now()
    can_submit = (not is_archived) and (assignment.allows_multiple_attempts or not has_existing_attempt)

    if request.method == "POST":
        if is_archived:
            messages.error(request, "This assignment is archived. New submissions are closed.")
            return redirect("take_quiz_assignment", assignment_id=assignment.id)
        if not questions.exists():
            messages.error(request, "No assignment questions configured yet.")
            return redirect("view_assignments")
        if not can_submit:
            messages.error(request, "This assignment allows only one attempt.")
            return redirect("take_quiz_assignment", assignment_id=assignment.id)

        selected_answers = {}
        for question in questions:
            selected_option = request.POST.get(f"question_{question.id}", "").strip().upper()
            if selected_option not in {"A", "B", "C", "D"}:
                messages.error(request, "Please answer all assignment questions before submitting.")
                return redirect("take_quiz_assignment", assignment_id=assignment.id)
            selected_answers[question.id] = selected_option

        for question in questions:
            QuizAnswer.objects.update_or_create(
                question=question,
                student=request.user,
                defaults={"selected_option": selected_answers[question.id]}
            )

        evaluate_quiz_for_student(assignment, request.user)

        if has_existing_attempt:
            messages.success(request, "Assignment re-submitted successfully.")
        else:
            messages.success(request, "Assignment submitted successfully.")
        return redirect("view_assignments")

    question_rows = [
        {
            "question": question,
            "selected_option": existing_answers.get(question.id, ""),
        }
        for question in questions
    ]
    show_description = bool(assignment.description)
    if show_description and questions.exists():
        show_description = not bool(
            _parse_quiz_questions_from_description(assignment.description)
        )

    return render_for_device(request, "student/assignment/take_quiz.html", {
        "assignment": assignment,
        "questions": questions,
        "question_rows": question_rows,
        "can_submit": can_submit,
        "is_archived": is_archived,
        "show_description": show_description,
    })


@login_required
def submit_code_assignment(request, assignment_id):
    redirect_response = _ensure_student(request)
    if redirect_response:
        return redirect_response

    assignment = get_object_or_404(
        Assignment.objects.select_related("classroom"),
        id=assignment_id,
        classroom__students=request.user,
        assignment_type=Assignment.ASSIGNMENT_TYPE_CODE
    )
    is_archived = assignment.due_date < timezone.now()
    existing_submission = CodeSubmission.objects.filter(
        assignment=assignment,
        student=request.user
    ).first()
    can_submit = (not is_archived) and (assignment.allows_multiple_attempts or not existing_submission)

    # --- PARSING LOGIC FOR MULTIPLE PROBLEMS ---
    # Split the assignment description by "### Problem " headers.
    description_text = assignment.description or ""
    parts = re.split(r"(?im)^###\s*Problem\s+.*?(?:\r?\n|$)", description_text)
    
    problems = []
    # Re-extract headers to recombine with text for rendering
    headers = re.findall(r"(?im)^###\s*Problem\s+.*?(?:\r?\n|$)", description_text)
    
    if len(parts) > 1:
        # If the first part is empty or just preamble, handle it
        preamble = parts[0].strip()
        for i in range(len(headers)):
            content = headers[i] + parts[i+1]
            problems.append(content.strip())
        if preamble and not problems:
            problems.append(preamble)
    else:
        problems.append(description_text)
        
    delimiter = "\n\n# --- PROBLEM SEPARATOR ---\n\n"
    
    if request.method == "POST":
        if is_archived:
            messages.error(request, "This coding assignment is archived. New submissions are closed.")
            return redirect("submit_code_assignment", assignment_id=assignment.id)
        if not can_submit:
            messages.error(request, "This coding assignment allows only one attempt.")
            return redirect("submit_code_assignment", assignment_id=assignment.id)

        language = request.POST.get("language", "python").strip() or "python"
        
        # Combine all code editors
        code_snippets = []
        for i in range(len(problems)):
            snippet = request.POST.get(f"code_{i}", "").rstrip()
            code_snippets.append(snippet)
            
        combined_code = delimiter.join(code_snippets).strip()

        if not combined_code:
            messages.error(request, "Code cannot be empty.")
            return redirect("submit_code_assignment", assignment_id=assignment.id)

        if existing_submission:
            existing_submission.code = combined_code
            existing_submission.language = language
            existing_submission.save(update_fields=["code", "language"])
            sync_code_submission_record(existing_submission, evaluation_type="manual")
            success_message = "Code re-submitted successfully."
        else:
            code_submission = CodeSubmission.objects.create(
                assignment=assignment,
                student=request.user,
                code=combined_code,
                language=language,
            )
            sync_code_submission_record(code_submission, evaluation_type="manual")
            success_message = "Code submitted successfully."
        messages.success(request, success_message)
        return redirect("view_assignments")

    # Split existing code if it exists
    existing_codes = []
    if existing_submission and existing_submission.code:
        existing_codes = existing_submission.code.split(delimiter)
        
    # Pad existing codes with empty strings if necessary
    while len(existing_codes) < len(problems):
        existing_codes.append("")
        
    problem_data = []
    for i, prob_text in enumerate(problems):
        problem_data.append({
            "index": i,
            "text": prob_text,
            "code": existing_codes[i] if i < len(existing_codes) else ""
        })

    return render_for_device(request, "student/assignment/submit_code.html", {
        "assignment": assignment,
        "existing_submission": existing_submission,
        "can_submit": can_submit,
        "is_archived": is_archived,
        "problem_data": problem_data,
        "preamble": preamble if len(parts) > 1 and parts[0].strip() else None,
    })


@login_required
def student_profile(request):

    profile, _ = StudentProfile.objects.get_or_create(user=request.user)

    return render_for_device(
        request,
        "student/profile.html",
        {
            "profile": profile,
            "recent_login_2fa_otp": has_recent_login_2fa_otp(request.session),
        },
    )


@login_required
def edit_student_profile(request):

    profile, _ = StudentProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":

        request.user.username = request.POST.get("username", request.user.username)
        request.user.email = request.POST.get("email", request.user.email)
        request.user.save()

        profile.phone_number = request.POST.get("phone_number", "")
        profile.address = request.POST.get("address", "")
        profile.course = request.POST.get("course", "")
        profile.batch = request.POST.get("batch", "")
        profile.student_id = request.POST.get("student_id", "")

        dob_value = request.POST.get("date_of_birth")
        profile.date_of_birth = dob_value or None

        profile.gender = request.POST.get("gender", "")
        profile.parent_name = request.POST.get("parent_name", "")
        profile.parent_phone = request.POST.get("parent_phone", "")
        profile.parent_email = request.POST.get("parent_email", "")
        profile.guardian_relation = request.POST.get("guardian_relation", "")

        if request.FILES.get("profile_picture"):
            profile_picture = request.FILES.get("profile_picture")
            try:
                validate_profile_image(profile_picture)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return redirect("edit_student_profile")
            profile.profile_picture = profile_picture

        profile.save()

        return redirect("student_profile")

    return render_for_device(request, "student/update.html", {"profile": profile})
