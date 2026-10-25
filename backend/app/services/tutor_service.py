"""Interactive "Coach" tutor (ported from tutor.js).

A multi-turn chat tied to one lesson + the acting user. Coach teaches in small
bites, reacts to the student's ACTUAL typed answers, and guides them to produce
the deliverable THEMSELVES. The anti-copy-paste rule is absolute and verbatim:
Coach NEVER writes the student's answer/essay/solution.

Works fully offline: with NO GEMINI_API_KEY the opening + replies come from
deterministic on-persona mocks, so the whole experience runs with no network.
"""
from __future__ import annotations

from ..core.config import settings
from ..db import repository as repo
from ..integrations.gemini_service import GeminiService, NoApiKey, Overloaded
from ..web.framework import HttpError
from . import ai_mock
from .preferences_service import user_profile_for_ai

_STYLE_GUIDANCE = {
    "visual": 'This student leans VISUAL — paint quick mental pictures, describe diagrams, use spatial language.',
    "auditory": 'This student leans AUDITORY — talk it through like you are saying it aloud, use rhythm and little verbal mnemonics.',
    "reading": 'This student leans READING/WRITING — be precise with wording, offer crisp definitions, invite them to put things in writing.',
    "kinesthetic": 'This student leans KINESTHETIC — get them DOING a tiny step immediately, learn-by-trying, concrete hands-on moves.',
}


def _learner_block(styles: list[str], notes: str) -> str:
    if not styles and not notes:
        return ""
    style_lines = "\n".join(f"- {_STYLE_GUIDANCE.get(s, s)}" for s in styles)
    out = "\nWHO YOU ARE TUTORING (adapt tone + examples, never change the rules):\n"
    out += (style_lines if styles else "- No stated learning-style preference; keep it balanced.")
    if notes:
        out += f'\n- The student also told us: "{notes}" — honor this.'
    return out


def _system_prompt(assignment: dict, lesson: dict, styles: list[str], notes: str) -> str:
    return (
        'You are "Coach", the interactive tutor inside learning++. You are a BLEND of two things:\n'
        "1) a warm, encouraging human tutor who chats naturally, and\n"
        "2) a bite-size challenge GAME that gives instant, game-like feedback.\n\n"
        "Your mission: actually TEACH this lesson's concept and guide the student to produce\n"
        "the real deliverable IN THEIR OWN WORDS. You are the opposite of a copy-paste answer bot.\n\n"
        "HARD RULES (never break these):\n"
        "- NEVER write the student's answer, essay, or solution for them. Not even \"as an example\".\n"
        '  If they ask you to "just give the answer", warmly refuse and turn it back into a small step.\n'
        "- Teach in SMALL bites: one idea or one question per turn. Never dump a wall of text.\n"
        "- Always react to what the student ACTUALLY typed. Celebrate specifics when right; nudge\n"
        "  with a hint or simpler sub-question when off — never just say \"wrong\".\n"
        "- Keep each turn SHORT and lively (usually 2-5 sentences). Use the occasional emoji sparingly.\n"
        "  End most turns with a single clear question or a tiny challenge to attempt.\n"
        "- Progressively steer toward the real deliverable; have THEM draft it, then give feedback.\n"
        "- Stay on THIS lesson. Be honest if unsure; never invent fake facts.\n"
        f"{_learner_block(styles, notes)}\n\n"
        "THE ASSIGNMENT (context — do not solve it for them):\n"
        f"Title: {assignment.get('title', 'unknown')}\n"
        f"Due: {assignment.get('due_at', 'unknown')}\n"
        f"Description: {assignment.get('description') or '(none provided)'}\n\n"
        "THIS LESSON:\n"
        f"Title: {lesson.get('title', 'unknown')} (about {lesson.get('est_minutes', 10)} minutes)\n\n"
        "Stay in character as Coach for the whole conversation."
    )


def get_lesson_context(lesson_id: int) -> tuple[dict, dict]:
    lesson = repo.get_lesson(lesson_id)
    if lesson is None:
        raise HttpError(404, "lesson not found")
    assignment = repo.get_assignment(lesson["assignment_id"]) or {}
    return lesson, assignment


def get_history(lesson_id: int, user_id: int | None) -> list[dict]:
    rows = repo.list_tutor_messages(lesson_id, user_id)
    return [{"id": r["id"], "role": r["role"], "content": r["content"],
             "createdAt": r["created_at"]} for r in rows]


def reset_session(lesson_id: int, user_id: int | None) -> int:
    return repo.delete_tutor_messages(lesson_id, user_id)


def _to_gemini_history(rows: list[dict]) -> list[dict]:
    return [{"role": "model" if r["role"] == "model" else "user", "text": r["content"]} for r in rows]


def start_session(lesson_id: int, user_id: int | None, reset: bool = False) -> dict:
    lesson, assignment = get_lesson_context(lesson_id)
    if reset:
        reset_session(lesson_id, user_id)

    existing = get_history(lesson_id, user_id)
    if existing and not reset:
        return {"lessonId": lesson_id, "lessonTitle": lesson["title"],
                "resumed": True, "history": existing}

    prof = user_profile_for_ai(user_id)
    styles, notes = prof["learningStyles"], prof["learningNotes"]
    svc = GeminiService()
    model_used = "mock"
    if svc.use_mock:
        text = ai_mock.mock_tutor_opening(lesson["title"], styles)
    else:  # pragma: no cover - network path
        system = _system_prompt(assignment, lesson, styles, notes)
        kickoff = (
            "Begin the session. Greet the student warmly, name what we are about to tackle in one "
            "friendly line, then teach the FIRST tiny idea and immediately hit them with one small "
            "question or micro-challenge to attempt. Keep it to 2-4 sentences."
        )
        try:
            res = svc.generate_text(prompt=kickoff, system=system,
                                    temperature=settings.TUTOR_TEMPERATURE, history=[])
            text, model_used = res["text"], res["model_used"]
        except (NoApiKey, Overloaded):
            text = ai_mock.mock_tutor_opening(lesson["title"], styles)

    repo.insert_tutor_message(lesson_id, user_id, "model", text)
    return {"lessonId": lesson_id, "lessonTitle": lesson["title"], "resumed": False,
            "modelUsed": model_used, "history": get_history(lesson_id, user_id)}


def send_message(lesson_id: int, user_id: int | None, message) -> dict:
    text = str(message or "").strip()
    if not text:
        raise HttpError(400, "message is required")
    lesson, assignment = get_lesson_context(lesson_id)

    prior = get_history(lesson_id, user_id)
    # Persist the student's turn first so it is not lost even if Gemini errors.
    repo.insert_tutor_message(lesson_id, user_id, "user", text)

    prof = user_profile_for_ai(user_id)
    styles, notes = prof["learningStyles"], prof["learningNotes"]
    svc = GeminiService()
    model_used = "mock"
    if svc.use_mock:
        reply = ai_mock.mock_tutor_reply(text)
    else:  # pragma: no cover - network path
        system = _system_prompt(assignment, lesson, styles, notes)
        try:
            res = svc.generate_text(prompt=text, system=system,
                                    temperature=settings.TUTOR_TEMPERATURE,
                                    history=_to_gemini_history(prior))
            reply, model_used = res["text"], res["model_used"]
        except (NoApiKey, Overloaded):
            reply = ai_mock.mock_tutor_reply(text)

    repo.insert_tutor_message(lesson_id, user_id, "model", reply)
    return {"lessonId": lesson_id, "reply": reply, "modelUsed": model_used,
            "history": get_history(lesson_id, user_id)}
