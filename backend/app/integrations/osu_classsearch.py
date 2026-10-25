"""Schedule advisor backed by the OSU class-search API (mockable).

Recommends next-semester courses based on the student's current courses.
Offline it uses a small hard-coded prerequisite/sequence map.
"""
from __future__ import annotations

import logging

from ..core.config import settings

logger = logging.getLogger("learnpp.classsearch")

# code currently taken -> recommended next course
_NEXT_COURSE_MAP: dict[str, dict] = {
    "CSE 2221": {"code": "CSE 2231", "title": "Software II: Software Development & Design",
                 "credit_hours": 4,
                 "reason": "Direct sequel to Software I; continues the components methodology."},
    "MATH 1151": {"code": "MATH 1172", "title": "Engineering Mathematics A",
                  "credit_hours": 5,
                  "reason": "Natural next step after Calculus I for engineering majors."},
    "ENGR 1182": {"code": "ENGR 2000", "title": "Engineering Technical Communications",
                  "credit_hours": 3,
                  "reason": "Follows the first-year engineering sequence."},
}


class OSUClassSearch:
    def __init__(self) -> None:
        self.use_mock = settings.USE_MOCK_INTEGRATIONS

    def recommend_next(self, current_course_codes: list[str]) -> list[dict]:
        if self.use_mock:
            return self._mock_recommend(current_course_codes)
        try:  # pragma: no cover - requires network
            return self._real_recommend(current_course_codes)
        except Exception as exc:  # pragma: no cover
            logger.warning("Class search failed (%s); using mock.", exc)
            return self._mock_recommend(current_course_codes)

    def _real_recommend(self, codes: list[str]) -> list[dict]:  # pragma: no cover
        # Query https://content.osu.edu/v2/classes/search on the VM.
        raise NotImplementedError("Wire up OSU class-search API on the VM.")

    def _mock_recommend(self, codes: list[str]) -> list[dict]:
        recs: list[dict] = []
        for code in codes:
            if code in _NEXT_COURSE_MAP:
                recs.append(_NEXT_COURSE_MAP[code])
        if not recs:
            recs.append({
                "code": "GE 1100", "title": "General Education Elective",
                "credit_hours": 3,
                "reason": "Keep progressing on GE requirements while planning your major path.",
            })
        return recs
