"""Auto-generation of interactive lessons for assignments due within 7 days.

REPLACES the old static concept/tip/quiz generator. Now an assignment due soon
is run through the ported lesson engine: decompose -> lessons+blocks -> resolve
resource blocks (video/excerpt). The gamified staged flow, Coach tutor, and
compile all read from those lessons/blocks.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..db import repository as repo
from .decompose_service import decompose_assignment
from .resolve_service import resolve_resources

logger = logging.getLogger("learnpp.lessons")

LESSON_WINDOW_DAYS = 7


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _due_within_window(due_at: str) -> bool:
    now = datetime.now(timezone.utc)
    due = _parse_dt(due_at)
    return now <= due <= now + timedelta(days=LESSON_WINDOW_DAYS)


def generate_lesson_for_assignment(assignment: dict, user_id: int | None = None,
                                   *, force: bool = False) -> dict:
    """Decompose an assignment into interactive lessons if it has none."""
    if repo.assignment_has_lessons(assignment["id"]) and not force:
        return _assignment_lessons(assignment["id"])

    # Learning-style preferences tailor the lesson mix when a student is known.
    from .preferences_service import user_profile_for_ai
    prof = user_profile_for_ai(user_id)
    decompose_assignment(assignment, user_id, prof["learningStyles"], prof["learningNotes"])
    # Resolve video/reading resources (keyless fallbacks offline).
    try:
        resolve_resources(assignment["id"])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("resource resolution failed for assignment %s (%s)", assignment["id"], exc)
    return _assignment_lessons(assignment["id"])


def _assignment_lessons(assignment_id: int) -> dict:
    lessons = repo.list_lessons_for_assignment(assignment_id)
    for l in lessons:
        l["blocks"] = repo.list_lesson_blocks(l["id"])
    return {"assignmentId": assignment_id, "lessons": lessons}


def autogenerate_due_soon() -> int:
    """Generate interactive lessons for every assignment due within 7 days."""
    created = 0
    for a in repo.list_all_assignments():
        if not repo.assignment_has_lessons(a["id"]) and _due_within_window(a["due_at"]):
            generate_lesson_for_assignment(a)
            created += 1
    logger.info("Auto-generated interactive lessons for %d due-soon assignments.", created)
    return created
