"""Access-control helpers enforcing the PRD Success Criteria."""
from __future__ import annotations

from ..db import repository as repo
from .framework import HttpError, Request


def require_course_access(req: Request, course_id: int) -> dict:
    """Members of the course (students or its professor) + admins only.

    Recruiters never get course access.
    """
    user = req.current_user()
    if user["role"] == "admin":
        return user
    if user["role"] == "recruiter":
        raise HttpError(403, "Recruiters cannot access course content")
    if repo.get_enrollment(user["id"], course_id) is None:
        raise HttpError(403, "You are not enrolled in this course")
    return user


def require_course_instructor(req: Request, course_id: int) -> dict:
    """Only the course's professor (or an admin) may moderate it."""
    user = req.current_user()
    if user["role"] == "admin":
        return user
    enr = repo.get_enrollment(user["id"], course_id)
    if enr is None or enr["role"] != "professor":
        raise HttpError(403, "Only the course instructor can perform this action")
    return user
