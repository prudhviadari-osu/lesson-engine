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
MIN_DAILY_MINUTES = 60    # 1 hour
MAX_DAILY_MINUTES = 360   # 6 hours
DEFAULT_DAILY_MINUTES = 120


def validate_daily_minutes(value) -> int:
    """Clamp the student's total daily study budget to 1-6 hours (minutes)."""
    if value is None:
        return DEFAULT_DAILY_MINUTES
    try:
        m = int(round(float(value)))
    except (TypeError, ValueError):
        raise HttpError(400, "dailyMinutes must be a number of minutes")
    if m < MIN_DAILY_MINUTES or m > MAX_DAILY_MINUTES:
        raise HttpError(400, f"dailyMinutes must be between {MIN_DAILY_MINUTES} (1h) and {MAX_DAILY_MINUTES} (6h)")
    return m


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
        return {"learningStyles": [], "learningNotes": "", "dailyMinutes": DEFAULT_DAILY_MINUTES}
    dm = row["daily_minutes"] if row.get("daily_minutes") is not None else DEFAULT_DAILY_MINUTES
    return {
        "learningStyles": json.loads(row["learning_styles"] or "[]"),
        "learningNotes": row["learning_notes"] or "",
        "dailyMinutes": max(MIN_DAILY_MINUTES, min(MAX_DAILY_MINUTES, int(dm))),
    }


def set_preferences(user_id: int, learning_styles, learning_notes, daily_minutes=None) -> dict:
    styles = validate_styles(learning_styles)
    notes = str(learning_notes or "")
    # Preserve existing daily_minutes if the caller didn't send one.
    if daily_minutes is None:
        existing = repo.get_learning_preferences(user_id)
        minutes = (existing["daily_minutes"] if existing and existing.get("daily_minutes") is not None
                   else DEFAULT_DAILY_MINUTES)
        minutes = max(MIN_DAILY_MINUTES, min(MAX_DAILY_MINUTES, int(minutes)))
    else:
        minutes = validate_daily_minutes(daily_minutes)
    repo.upsert_learning_preferences(user_id, json.dumps(styles), notes, minutes)
    return get_preferences(user_id)


def user_profile_for_ai(user_id: int | None) -> dict:
    """Shape consumed by the decompose + tutor prompts."""
    if user_id is None:
        return {"learningStyles": [], "learningNotes": ""}
    return get_preferences(user_id)
