"""Decompose an assignment into lessons + blocks (ported from decompose.js).

AI designs an ordered sequence of ~10-15 min mini-lessons, each a list of
typed blocks (video | excerpt | scaffold_q | draft | flashcards). The learner's
style preferences tailor the block mix. STRICT RULE carried over verbatim: a
"draft" block gives an INSTRUCTION for the student to write their OWN work and
never includes a model answer.
"""
from __future__ import annotations

import json
import logging

from ..db import repository as repo
from ..integrations.gemini_service import GeminiService, NoApiKey, Overloaded
from ..web.framework import HttpError
from . import ai_mock

logger = logging.getLogger("learnpp.decompose")

_STYLE_GUIDANCE = {
    "visual": "Favor 'video' blocks and visual explanations. Prefer diagrams/animations described in video queries.",
    "auditory": "Favor 'video' blocks (to be heard) and phrase scaffold questions as if explaining aloud; lean on spoken/lecture-style content.",
    "reading": "Favor 'excerpt' reading blocks and written 'scaffold_q' reflection; fewer videos.",
    "kinesthetic": "Favor 'draft' and hands-on practice blocks where the student DOES the work; more applied problems, earlier.",
}


def _learner_block(styles: list[str], notes: str) -> str:
    if not styles and not notes:
        return ""
    style_lines = "\n".join(f"  - {s}: {_STYLE_GUIDANCE.get(s, '')}" for s in styles)
    out = "\nLEARNER PROFILE (tailor the lesson mix to this student, WITHOUT ever writing their answers):\n"
    out += (f"Preferred learning style(s):\n{style_lines}\n" if styles else "No specific style preference.\n")
    if notes:
        out += f'The student also says: "{notes}" — honor this in tone, pacing, and examples.\n'
    out += "When two styles are given, blend them. Keep lessons ~10-15 min regardless of style.\n"
    return out


def _build_prompt(assignment: dict, styles: list[str], notes: str) -> str:
    return (
        'You are the lesson designer for "learning++", a study tool whose PURPOSE is to make\n'
        "students genuinely learn their coursework in small daily chunks — the OPPOSITE of\n"
        "copy-pasting an AI answer. You break an assignment into a sequence of ~10-15 minute\n"
        "mini-lessons a busy student can do on the go.\n"
        f"{_learner_block(styles, notes)}\n"
        "STRICT RULES:\n"
        "- NEVER write the student's answer or the deliverable for them. 'draft' blocks give an\n"
        "  INSTRUCTION for the student to write their OWN work; never include a model answer.\n"
        "- Break the assignment down as finely as it allows. A large assignment = more lessons.\n"
        "- Each lesson is one sitting of ~10-15 minutes. Order them so earlier lessons teach the\n"
        "  concept and later lessons apply it to produce pieces of the actual deliverable.\n"
        "- Block types: 'video' (provide videoQuery), 'excerpt' (provide excerptTopic),\n"
        "  'scaffold_q' (provide prompt + optional hint), 'draft' (provide instruction + optional\n"
        "  rubricHint), 'flashcards' (provide cards as {front, back} pairs).\n"
        "Return STRICT JSON: {\"lessons\":[{\"title\":str,\"estMinutes\":int,\"blocks\":[...]}]}.\n\n"
        "ASSIGNMENT:\n"
        f"Title: {assignment.get('title')}\n"
        f"Type: {assignment.get('kind', 'assignment')}\n"
        f"Due: {assignment.get('due_at', 'unknown')}\n\n"
        f"Description:\n{assignment.get('description') or '(no description provided)'}\n\n"
        "Produce the lessons now."
    )


def _clamp_minutes(m) -> int:
    try:
        n = round(float(m))
    except (TypeError, ValueError):
        return 12
    return min(20, max(5, n))


def _normalize_block(b: dict) -> dict:
    t = b.get("type")
    if t == "video":
        return {"query": b.get("videoQuery", ""), "videoId": None, "title": None,
                "channel": None, "url": None, "embedUrl": None, "thumbnail": None, "resolved": False}
    if t == "excerpt":
        return {"topic": b.get("excerptTopic", ""), "attachmentId": None, "page": None,
                "heading": None, "text": None, "url": None, "resolved": False}
    if t == "scaffold_q":
        return {"prompt": b.get("prompt", ""), "hint": b.get("hint", ""), "savesTo": "answer"}
    if t == "draft":
        return {"instruction": b.get("instruction", ""), "rubricHint": b.get("rubricHint", ""), "savesTo": "answer"}
    if t == "flashcards":
        cards = b.get("cards") or []
        return {"cards": [{"front": c.get("front", ""), "back": c.get("back", "")} for c in cards]}
    return {}


def decompose_assignment(assignment: dict, user_id: int | None, styles: list[str], notes: str) -> dict:
    """Decompose + persist lessons/blocks for an assignment. Replaces any existing."""
    svc = GeminiService()
    cached = False
    generated_by = "mock"

    if svc.use_mock:
        data = ai_mock.mock_decompose(assignment, styles, notes)
    else:  # pragma: no cover - network path
        try:
            profile_key = json.dumps({"s": styles, "n": notes})
            res = svc.generate_json(
                prompt=_build_prompt(assignment, styles, notes),
                cache_key_extra=f"decompose:{assignment['id']}:{profile_key}",
            )
            data = res["data"]
            cached = res["cached"]
            generated_by = "gemini"
        except (NoApiKey, Overloaded) as exc:
            logger.warning("decompose fell back to mock (%s)", exc)
            data = ai_mock.mock_decompose(assignment, styles, notes)
        except Exception as exc:
            logger.warning("decompose Gemini error (%s); using mock", exc)
            data = ai_mock.mock_decompose(assignment, styles, notes)

    lessons = data.get("lessons") if isinstance(data, dict) else None
    if not lessons:
        raise HttpError(502, "lesson generation returned no lessons")

    assignment_id = assignment["id"]
    repo.delete_lessons_for_assignment(assignment_id)
    for li, lesson in enumerate(lessons):
        lesson_id = repo.create_lesson(
            assignment_id, li + 1,
            lesson.get("title") or f"Lesson {li + 1}",
            _clamp_minutes(lesson.get("estMinutes")),
            generated_by,
        )
        for bi, block in enumerate(lesson.get("blocks") or []):
            repo.create_lesson_block(
                lesson_id, bi + 1, block.get("type"),
                json.dumps(_normalize_block(block)),
            )

    out = _lessons_with_blocks(assignment_id)
    return {"cached": cached, "generatedBy": generated_by,
            "lessonCount": len(out), "lessons": out}


def _lessons_with_blocks(assignment_id: int) -> list[dict]:
    result = []
    for l in repo.list_lessons_for_assignment(assignment_id):
        blocks = [
            {"id": b["id"], "seq": b["seq"], "type": b["type"],
             "payload": json.loads(b["payload_json"])}
            for b in repo.list_lesson_blocks(l["id"])
        ]
        result.append({**l, "blocks": blocks})
    return result
