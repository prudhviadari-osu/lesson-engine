"""Planner + reflow (ported from planner.js).

Anti-procrastination core: schedule TODO lessons BACKWARD from each assignment's
due date, reserve a submission buffer, and cap daily load. Over-capacity days are
flagged, not silently crammed. Lessons that cannot fit land scheduled-but-flagged
(overflow). Unscheduling a lesson moves it to the backlog. Touches only
plan_entries — never lessons or answers.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..core.config import settings
from ..db import repository as repo


def _day_str(d: date) -> str:
    return d.isoformat()


def _add_days(d: date, n: int) -> date:
    return d + timedelta(days=n)


def _days_between(a: date, b: date) -> int:
    return (b - a).days


def _parse_due(due_at: str | None) -> date | None:
    if not due_at:
        return None
    try:
        return datetime.fromisoformat(due_at[:10]).date()
    except ValueError:
        try:
            return datetime.fromisoformat(due_at).date()
        except ValueError:
            return None


def generate_plan(user_id: int) -> dict:
    cap = settings.DAILY_CAP_MIN
    buffer_days = settings.SUBMISSION_BUFFER_DAYS
    lessons = repo.list_todo_lessons_for_user(user_id)
    version = repo.max_reflow_version() + 1

    today = date.today()
    day_load: dict[str, int] = {}
    overflow = []

    for l in lessons:
        repo.clear_plan_entry(l["lesson_id"])

    for l in lessons:
        est = l["est_minutes"]
        due = _parse_due(l.get("due_at"))
        if due:
            last_allowed = _add_days(due, -buffer_days)
        else:
            last_allowed = _add_days(today, 14)
        if last_allowed < today:
            last_allowed = today

        placed = False
        span = max(0, _days_between(today, last_allowed))
        for i in range(span + 1):
            d = _day_str(_add_days(today, i))
            load = day_load.get(d, 0)
            if load + est <= cap:
                repo.insert_plan_entry(l["lesson_id"], d, version)
                day_load[d] = load + est
                placed = True
                break
        if not placed:
            d = _day_str(last_allowed)
            repo.insert_plan_entry(l["lesson_id"], d, version)
            day_load[d] = day_load.get(d, 0) + est
            overflow.append({"lessonId": l["lesson_id"], "assignment": l.get("assignment"),
                             "reason": "over_capacity"})

    return get_plan(user_id, version=version, overflow=overflow)


def get_plan(user_id: int, version: int | None = None, overflow: list | None = None) -> dict:
    cap = settings.DAILY_CAP_MIN
    today = _day_str(date.today())

    scheduled = repo.list_scheduled_lessons_for_user(user_id)
    backlog = repo.list_backlog_lessons_for_user(user_id)

    by_date: dict[str, list] = {}
    for s in scheduled:
        by_date.setdefault(s["date"], []).append(s)
    days = []
    for d, lessons in by_date.items():
        load = sum(l["est_minutes"] for l in lessons)
        days.append({"date": d, "loadMinutes": load, "overCapacity": load > cap, "lessons": lessons})
    days.sort(key=lambda x: x["date"])

    warnings = [
        {"type": "over_capacity", "date": d["date"],
         "message": f"{d['date']} is over the {cap}-min daily cap — start earlier."}
        for d in days if d["overCapacity"]
    ]

    streak_row = repo.get_lesson_streak(today)
    return {
        "reflowVersion": version if version is not None else repo.max_reflow_version(),
        "today": today,
        "todayStreak": streak_row["completed_count"] if streak_row else 0,
        "dailyCapMin": cap,
        "submissionBufferDays": settings.SUBMISSION_BUFFER_DAYS,
        "days": days,
        "unscheduled": backlog,
        "overflow": overflow or [],
        "warnings": warnings,
    }


def unschedule_lesson(lesson_id: int) -> bool:
    return repo.clear_plan_entry(lesson_id) > 0


def reschedule_lesson(user_id: int, lesson_id: int) -> bool:
    cap = settings.DAILY_CAP_MIN
    buffer_days = settings.SUBMISSION_BUFFER_DAYS
    l = repo.get_lesson_for_user(user_id, lesson_id)
    if not l:
        return False

    repo.clear_plan_entry(lesson_id)
    today = date.today()
    due = _parse_due(l.get("due_at"))
    last_allowed = _add_days(due, -buffer_days) if due else _add_days(today, 14)
    if last_allowed < today:
        last_allowed = today

    loads = repo.current_day_loads_for_user(user_id)
    version = repo.max_reflow_version()
    span = max(0, _days_between(today, last_allowed))
    est = l["est_minutes"]
    for i in range(span + 1):
        d = _day_str(_add_days(today, i))
        if loads.get(d, 0) + est <= cap:
            repo.insert_plan_entry(lesson_id, d, version)
            return True
    repo.insert_plan_entry(lesson_id, _day_str(last_allowed), version)
    return True


def clear_plan(user_id: int) -> int:
    return repo.clear_plan_for_user(user_id)
