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
            {"canvas_course_id": "ECE2060-001", "code": "ECE 2060",
             "title": "Introduction to Digital Logic", "section": "001"},
            {"canvas_course_id": "CSE2221-001", "code": "CSE 2221",
             "title": "Software I: Software Components", "section": "001"},
            {"canvas_course_id": "MATH1151-012", "code": "MATH 1151",
             "title": "Calculus I", "section": "012"},
            {"canvas_course_id": "ENGR1182-040", "code": "ENGR 1182",
             "title": "Fundamentals of Engineering II", "section": "040"},
        ]
        assignments = [
            # The demo showcase assignment — the real ECE 2060 number-systems HW.
            # Its description carries the actual problems so the (offline) lesson
            # engine builds the deep mastery climb around the real questions.
            {"course_code": "ECE 2060", "title": "Problem 1 — Number Systems & Base Conversion",
             "kind": "assignment",
             "description": (
                 "ECE 2060 Autumn 2026. Show all steps. "
                 "1-1 Convert 79, 40, and 4769 (base 10) to base 2. "
                 "1-2 Convert 10101011 and 0100111011 (base 2) to base 10. "
                 "1-3 Convert 211(base 3), DE3A(base 16) to base 10; 42855 to hexadecimal; 93.27 to base 4. "
                 "1-4 Binary addition; 1-5 binary subtraction with borrows; 1-6 binary multiplication; "
                 "1-7 binary division. 1-8 Negative numbers: sign & magnitude and 2's complement "
                 "(N* = 2^n - N). 1-9 One's complement. 1-11 Adding 2's- and 1's-complement numbers. "
                 "1-10 Binary codes: Gray code power savings, 7-bit max, hex and ASCII."
             ),
             "due_at": now + timedelta(days=3)},
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
