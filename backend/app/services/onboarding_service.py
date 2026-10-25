"""Onboarding: sync a user's Canvas courses, assignments, and members.

Mirrors the PRD Playwright flow: scrape courses -> calendar assignments ->
course members/roles, persist them, enroll the user, and link any member
who already has a Learn++ account (e.g. professors) into the course.
"""
from __future__ import annotations

import logging

from ..db import repository as repo
from ..integrations import CanvasScraper

logger = logging.getLogger("learnpp.onboarding")


def _get_or_create_course(c: dict) -> dict:
    course = repo.get_course_by_code_section(c["code"], c["section"])
    if course is None:
        cid = repo.create_course(
            canvas_course_id=c.get("canvas_course_id"),
            code=c["code"],
            title=c["title"],
            section=c["section"],
            term=c.get("term", "AU25"),
        )
        course = repo.get_course(cid)
    return course


def sync_user_from_canvas(user: dict) -> dict:
    """Pull Canvas data for the user and persist courses/assignments/members."""
    scraper = CanvasScraper()
    data = scraper.scrape_student_data(
        user.get("osu_name_dot_number") or user["username"]
    )

    code_to_course: dict[str, dict] = {}
    for c in data["courses"]:
        course = _get_or_create_course(c)
        code_to_course[c["code"]] = course

        if repo.get_enrollment(user["id"], course["id"]) is None:
            role = "professor" if user["role"] == "professor" else "student"
            repo.create_enrollment(user["id"], course["id"], role)

    # Assignments from the Canvas calendar.
    for a in data["assignments"]:
        course = code_to_course.get(a["course_code"])
        if course is None:
            continue
        if repo.get_assignment_by_title(course["id"], a["title"]) is None:
            repo.create_assignment(
                course_id=course["id"],
                title=a["title"],
                description=a.get("description", ""),
                kind=a.get("kind", "assignment"),
                due_at=a["due_at"].isoformat() if hasattr(a["due_at"], "isoformat") else a["due_at"],
            )

    # Link known course members (e.g. professors who already have accounts).
    for code, members in data.get("members", {}).items():
        course = code_to_course.get(code)
        if course is None:
            continue
        for m in members:
            member_user = repo.get_user_by_name(m["name"])
            if member_user is None:
                continue
            if repo.get_enrollment(member_user["id"], course["id"]) is None:
                role = "professor" if m["role"] in {"professor", "instructor"} else "student"
                repo.create_enrollment(member_user["id"], course["id"], role)

    logger.info("Synced Canvas data for user %s.", user["email"])
    return {"courses": len(data["courses"]), "assignments": len(data["assignments"])}
