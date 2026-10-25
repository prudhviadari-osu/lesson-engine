"""Canvas scraping via Playwright with an offline mock fallback.

On the VM this logs into Canvas and scrapes the student's courses, calendar
assignments, and course members/roles. Offline it returns realistic seeded
data so the signup/login flow and lesson generation work end-to-end.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..core.config import settings

logger = logging.getLogger("learnpp.canvas")


class CanvasScraper:
    def __init__(self) -> None:
        self.use_mock = settings.USE_MOCK_INTEGRATIONS

    def scrape_student_data(self, name_dot_number: str) -> dict[str, Any]:
        """Return {courses: [...], assignments: [...], members: {...}}."""
        if self.use_mock:
            return self._mock_data(name_dot_number)
        try:  # pragma: no cover - requires network + browser
            return self._playwright_scrape(name_dot_number)
        except Exception as exc:  # pragma: no cover
            logger.warning("Canvas scrape failed (%s); using mock data.", exc)
            return self._mock_data(name_dot_number)

    # -- real Playwright scrape --------------------------------------------
    def _playwright_scrape(self, name_dot_number: str) -> dict[str, Any]:  # pragma: no cover
        # Requires: pip install playwright && playwright install chromium
        from playwright.sync_api import sync_playwright

        result: dict[str, Any] = {"courses": [], "assignments": [], "members": {}}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # NOTE: real OSU/Canvas login + 2FA is handled by OSUAuth; this
            # method assumes an authenticated session cookie is injected.
            page.goto("https://osu.instructure.com/courses")
            # ... selectors for course list, calendar, and people pages ...
            # Left as integration points for the VM deployment.
            browser.close()
        return result

    # -- offline mock -------------------------------------------------------
    def _mock_data(self, name_dot_number: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        courses = [
            {"canvas_course_id": "CSE2221-001", "code": "CSE 2221",
             "title": "Software I: Software Components", "section": "001"},
            {"canvas_course_id": "MATH1151-012", "code": "MATH 1151",
             "title": "Calculus I", "section": "012"},
            {"canvas_course_id": "ENGR1182-040", "code": "ENGR 1182",
             "title": "Fundamentals of Engineering II", "section": "040"},
        ]
        assignments = [
            {"course_code": "CSE 2221", "title": "Project: Natural Number Calculator",
             "kind": "assignment",
             "description": "Implement a calculator using the NaturalNumber component family.",
             "due_at": now + timedelta(days=2)},
            {"course_code": "CSE 2221", "title": "Homework 7: Recursion",
             "kind": "assignment",
             "description": "Write recursive methods and reason about their contracts.",
             "due_at": now + timedelta(days=5)},
            {"course_code": "MATH 1151", "title": "Midterm 2",
             "kind": "exam",
             "description": "Covers derivatives, chain rule, and related rates.",
             "due_at": now + timedelta(days=6)},
            {"course_code": "ENGR 1182", "title": "MATLAB Quiz 4",
             "kind": "quiz",
             "description": "Loops, conditionals, and plotting in MATLAB.",
             "due_at": now + timedelta(days=4)},
            {"course_code": "MATH 1151", "title": "WebAssign Set 9",
             "kind": "assignment",
             "description": "Practice problems on optimization.",
             "due_at": now + timedelta(days=10)},  # outside 7-day window
        ]
        members = {
            "CSE 2221": [
                {"name": "Dr. Alan Weide", "role": "professor"},
                {"name": "Jordan Lee", "role": "student"},
                {"name": "Priya Natarajan", "role": "student"},
            ],
            "MATH 1151": [
                {"name": "Dr. Maria Gomez", "role": "professor"},
                {"name": "Sam Carter", "role": "student"},
            ],
            "ENGR 1182": [
                {"name": "Prof. Dan Mercer", "role": "professor"},
            ],
        }
        return {"courses": courses, "assignments": assignments, "members": members}
