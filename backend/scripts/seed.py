"""Seed Learn++ with sample users, recruiter registry, and content.

Creates test accounts for every role (per the Success Criteria), populates the
authorized recruiter registry, syncs students' Canvas data, auto-generates
mini-lessons, and adds forum threads, projects, and announcements.

Run:  python -m backend.scripts.seed
Default password for every seeded account:  Password123
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.security import hash_password  # noqa: E402
from backend.app.db import repository as repo  # noqa: E402
from backend.app.db.database import init_db  # noqa: E402
from backend.app.services.lesson_service import autogenerate_due_soon  # noqa: E402
from backend.app.services.onboarding_service import sync_user_from_canvas  # noqa: E402
from backend.app.services.preferences_service import set_preferences  # noqa: E402

PW = "Password123"


def _user(**kw) -> dict:
    kw.setdefault("org_verified", 1)
    uid = repo.create_user(hashed_password=hash_password(PW), **kw)
    return repo.get_user(uid)


def main() -> None:
    init_db()
    if repo.count_users() > 0:
        print("Database already seeded; skipping.")
        return

    # --- Authorized recruiter registry (university-approved companies) ---
    for email, company in [
        ("recruiter.amazon@learnpp.test", "Amazon"),
        ("recruiter.google@learnpp.test", "Google"),
        ("recruiter.apple@learnpp.test", "Apple"),
        ("recruiter.microsoft@learnpp.test", "Microsoft"),
        ("recruiter.aep@learnpp.test", "AEP"),
        ("recruiter.honda@learnpp.test", "Honda"),
    ]:
        repo.add_registered_recruiter(email, company, "seed")

    # --- Professors (exist before student sync so they get linked) ---
    prof_weide = _user(
        email="weide.1@osu.edu", username="weide", full_name="Dr. Alan Weide",
        role="professor", osu_name_dot_number="weide.1",
        bio="Teaches Software I.", major="Computer Science & Engineering",
    )
    prof_gomez = _user(
        email="gomez.2@osu.edu", username="gomez", full_name="Dr. Maria Gomez",
        role="professor", osu_name_dot_number="gomez.2",
        bio="Calculus I instructor.", major="Mathematics",
    )

    # --- Admin ---
    _user(email="admin@osu.edu", username="admin",
          full_name="Learn++ Administrator", role="admin")

    # --- Students ---
    student = _user(
        email="buckeye.1@osu.edu", username="buckeye", full_name="Jordan Lee",
        role="student", osu_name_dot_number="buckeye.1",
        major="Computer Science & Engineering", grad_year=2027,
        github_url="https://github.com/jordanlee", bio="CSE sophomore.",
    )
    student2 = _user(
        email="scarlet.2@osu.edu", username="scarlet", full_name="Priya Natarajan",
        role="student", osu_name_dot_number="scarlet.2",
        major="Computer Science & Engineering", grad_year=2026,
    )

    # --- Recruiter accounts (on the registry) ---
    _user(email="recruiter.google@learnpp.test", username="googlerec",
          full_name="Taylor Kim (Google Recruiting)", role="recruiter", company="Google")
    _user(email="recruiter.amazon@learnpp.test", username="amazonrec",
          full_name="Morgan Diaz (Amazon Recruiting)", role="recruiter", company="Amazon")

    # --- Learning-style preferences (tailors the AI lesson engine) ---
    set_preferences(student["id"], ["visual", "kinesthetic"],
                    "I learn best with diagrams and by trying things hands-on.")
    set_preferences(student2["id"], ["reading"], "")

    # --- Canvas sync for students (creates courses/assignments/members) ---
    sync_user_from_canvas(student)
    sync_user_from_canvas(student2)

    # --- Auto-generate interactive lessons for assignments due within 7 days.
    # Each assignment is decomposed into a staged flow (intro -> watch -> read
    # -> challenge -> draft -> complete) by the ported lesson engine. ---
    created = autogenerate_due_soon()
    print(f"Auto-generated interactive lessons for {created} due-soon assignments.")

    # --- A guided project + a published showcase project ---
    cse = repo.get_course_by_code_section("CSE 2221", "001")
    if cse:
        repo.create_project(
            project_type="guided", course_id=cse["id"],
            title="Guided: Build a Queue with NaturalNumber",
            description="A scaffolded mini-project reinforcing recent Software I topics.",
        )
    repo.create_project(
        project_type="showcase", owner_id=student["id"],
        title="CampusEats — Dining Hall Wait-Time Tracker",
        description="Full-stack app predicting dining hall wait times from crowd data.",
        repo_url="https://github.com/jordanlee/campuseats",
        tech_stack="React, FastAPI, PostgreSQL", published=True,
    )

    # --- Some forum activity + announcements ---
    if cse:
        tid = repo.create_thread(cse["id"], student["id"],
                                 "Stuck understanding the NaturalNumber contract",
                                 "Anyone have tips for reasoning about the kernel methods?")
        repo.create_post(tid, prof_weide["id"],
                         "Great question — start from the mathematical model in the docs.")
        repo.create_announcement(
            course_id=cse["id"], author_id=prof_weide["id"],
            title="Software I Exam Review — Thursday 6pm",
            body="Optional review session in Dreese Labs 264. Bring questions!",
            category="study", location="Dreese Labs 264",
            event_at=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        )
    repo.create_announcement(
        course_id=None, author_id=prof_gomez["id"],
        title="University-wide Finals Study Jam (Discord)",
        body="Join the #study-jam voice channel for a group cram session.",
        category="event", location="Discord",
        event_at=(datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
    )

    print("Seed complete.")
    print(f"Login password for all accounts: {PW}")
    print("Students/professors use OSU 2FA code: 000000")


if __name__ == "__main__":
    main()
