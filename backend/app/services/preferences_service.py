"""Per-user learning-style preferences (ported from the JS users.js).

Students pick at most 2 of visual/auditory/reading/kinesthetic plus optional
free-text notes. These tailor the AI (decompose block mix + Coach tone) WITHOUT
ever changing the anti-copy-paste rules.
"""
from __future__ import annotations

import json

from ..db import repository as repo
from ..web.framework import HttpError

VALID_STYLES = ["visual", "auditory", "reading", "kinesthetic"]
MAX_STYLES = 2


def validate_styles(styles) -> list[str]:
    if styles is None:
        return []
    if not isinstance(styles, list):
        raise HttpError(400, "learningStyles must be an array")
    cleaned: list[str] = []
    for s in styles:
        v = str(s).lower().strip()
        if v and v not in cleaned:
            cleaned.append(v)
    for s in cleaned:
        if s not in VALID_STYLES:
            raise HttpError(400, f"invalid learning style '{s}'. Allowed: {', '.join(VALID_STYLES)}")
    if len(cleaned) > MAX_STYLES:
        raise HttpError(400, f"choose at most {MAX_STYLES} learning styles (got {len(cleaned)})")
    return cleaned


def get_preferences(user_id: int) -> dict:
    row = repo.get_learning_preferences(user_id)
    if row is None:
        return {"learningStyles": [], "learningNotes": ""}
    return {
        "learningStyles": json.loads(row["learning_styles"] or "[]"),
        "learningNotes": row["learning_notes"] or "",
    }


def set_preferences(user_id: int, learning_styles, learning_notes) -> dict:
    styles = validate_styles(learning_styles)
    notes = str(learning_notes or "")
    repo.upsert_learning_preferences(user_id, json.dumps(styles), notes)
    return get_preferences(user_id)


def user_profile_for_ai(user_id: int | None) -> dict:
    """Shape consumed by the decompose + tutor prompts."""
    if user_id is None:
        return {"learningStyles": [], "learningNotes": ""}
    return get_preferences(user_id)
