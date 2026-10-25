"""Repository functions: all CRUD for Learn++ entities.

Keeps SQL in one place so the HTTP layer stays thin and the storage engine
is swappable (SQLite now, MySQL on the VM).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from . import database as db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------- users -------------------------------------
def create_user(**kw: Any) -> int:
    cols = (
        "email", "username", "full_name", "hashed_password", "role",
        "org_verified", "osu_name_dot_number", "bio", "avatar_url",
        "github_url", "linkedin_url", "major", "grad_year", "company",
    )
    values = [kw.get(c) for c in cols]
    placeholders = ", ".join("?" for _ in cols)
    return db.execute(
        f"INSERT INTO users ({', '.join(cols)}) VALUES ({placeholders})", values
    )


def get_user(user_id: int) -> dict | None:
    return db.row_to_dict(db.query_one("SELECT * FROM users WHERE id = ?", (user_id,)))


def get_user_by_email(email: str) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM users WHERE email = ?", (email,))
    )


def get_user_by_username(username: str) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM users WHERE username = ?", (username,))
    )


def get_user_by_name(full_name: str) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM users WHERE full_name = ?", (full_name,))
    )


def update_user(user_id: int, fields: dict[str, Any]) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{k} = ?" for k in fields)
    db.execute(
        f"UPDATE users SET {assignments} WHERE id = ?",
        [*fields.values(), user_id],
    )


def count_users() -> int:
    return db.query_one("SELECT COUNT(*) AS c FROM users")["c"]


# ------------------------- recruiter registry ------------------------------
def add_registered_recruiter(email: str, company: str, added_by: str | None) -> int:
    return db.execute(
        "INSERT INTO registered_recruiters (email, company, added_by) VALUES (?, ?, ?)",
        (email, company, added_by),
    )


def get_registered_recruiter(email: str) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM registered_recruiters WHERE email = ?", (email,))
    )


def list_registered_recruiters() -> list[dict]:
    return db.rows_to_dicts(db.query_all("SELECT * FROM registered_recruiters"))


# ------------------------------- courses -----------------------------------
def get_course(course_id: int) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM courses WHERE id = ?", (course_id,))
    )


def get_course_by_code_section(code: str, section: str) -> dict | None:
    return db.row_to_dict(
        db.query_one(
            "SELECT * FROM courses WHERE code = ? AND section = ?", (code, section)
        )
    )


def create_course(**kw: Any) -> int:
    return db.execute(
        "INSERT INTO courses (canvas_course_id, code, title, section, term) "
        "VALUES (?, ?, ?, ?, ?)",
        (kw.get("canvas_course_id"), kw["code"], kw["title"],
         kw["section"], kw.get("term", "AU25")),
    )


def list_all_courses() -> list[dict]:
    return db.rows_to_dicts(db.query_all("SELECT * FROM courses ORDER BY code"))


def list_user_courses(user_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT c.* FROM courses c JOIN enrollments e ON e.course_id = c.id "
        "WHERE e.user_id = ? ORDER BY c.code",
        (user_id,),
    ))


# ----------------------------- enrollments ---------------------------------
def get_enrollment(user_id: int, course_id: int) -> dict | None:
    return db.row_to_dict(db.query_one(
        "SELECT * FROM enrollments WHERE user_id = ? AND course_id = ?",
        (user_id, course_id),
    ))


def create_enrollment(user_id: int, course_id: int, role: str) -> int:
    return db.execute(
        "INSERT INTO enrollments (user_id, course_id, role) VALUES (?, ?, ?)",
        (user_id, course_id, role),
    )


def list_course_members(course_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT u.id AS user_id, u.full_name, e.role "
        "FROM enrollments e JOIN users u ON u.id = e.user_id "
        "WHERE e.course_id = ? ORDER BY e.role, u.full_name",
        (course_id,),
    ))


# ----------------------------- assignments ---------------------------------
def create_assignment(**kw: Any) -> int:
    return db.execute(
        "INSERT INTO assignments (course_id, title, description, kind, due_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (kw["course_id"], kw["title"], kw.get("description", ""),
         kw.get("kind", "assignment"), kw["due_at"]),
    )


def get_assignment(assignment_id: int) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM assignments WHERE id = ?", (assignment_id,))
    )


def get_assignment_by_title(course_id: int, title: str) -> dict | None:
    return db.row_to_dict(db.query_one(
        "SELECT * FROM assignments WHERE course_id = ? AND title = ?",
        (course_id, title),
    ))


def list_course_assignments(course_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT * FROM assignments WHERE course_id = ? ORDER BY due_at",
        (course_id,),
    ))


def list_all_assignments() -> list[dict]:
    return db.rows_to_dicts(db.query_all("SELECT * FROM assignments"))


# ======================= lesson engine (ported) ===========================
# --- lessons + blocks ---
def get_lesson(lesson_id: int) -> dict | None:
    return db.row_to_dict(db.query_one("SELECT * FROM lessons WHERE id = ?", (lesson_id,)))


def list_lessons_for_assignment(assignment_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT * FROM lessons WHERE assignment_id = ? ORDER BY seq", (assignment_id,)
    ))


def create_lesson(assignment_id: int, seq: int, title: str, est_minutes: int,
                  generated_by: str = "mock") -> int:
    return db.execute(
        "INSERT INTO lessons (assignment_id, seq, title, est_minutes, status, generated_by) "
        "VALUES (?, ?, ?, ?, 'todo', ?)",
        (assignment_id, seq, title, est_minutes, generated_by),
    )


def delete_lessons_for_assignment(assignment_id: int) -> None:
    db.execute("DELETE FROM lessons WHERE assignment_id = ?", (assignment_id,))


def set_lesson_status(lesson_id: int, status: str) -> None:
    db.execute("UPDATE lessons SET status = ? WHERE id = ?", (status, lesson_id))


def create_lesson_block(lesson_id: int, seq: int, type_: str, payload_json: str) -> int:
    return db.execute(
        "INSERT INTO lesson_blocks (lesson_id, seq, type, payload_json) VALUES (?, ?, ?, ?)",
        (lesson_id, seq, type_, payload_json),
    )


def list_lesson_blocks(lesson_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT * FROM lesson_blocks WHERE lesson_id = ? ORDER BY seq", (lesson_id,)
    ))


def get_lesson_block(block_id: int) -> dict | None:
    return db.row_to_dict(db.query_one("SELECT * FROM lesson_blocks WHERE id = ?", (block_id,)))


def update_lesson_block_payload(block_id: int, payload_json: str) -> None:
    db.execute("UPDATE lesson_blocks SET payload_json = ? WHERE id = ?", (payload_json, block_id))


def list_resource_blocks(assignment_id: int, types: tuple[str, ...]) -> list[dict]:
    placeholders = ", ".join("?" for _ in types)
    return db.rows_to_dicts(db.query_all(
        f"SELECT lb.* FROM lesson_blocks lb JOIN lessons l ON l.id = lb.lesson_id "
        f"WHERE l.assignment_id = ? AND lb.type IN ({placeholders}) ORDER BY l.seq, lb.seq",
        (assignment_id, *types),
    ))


def lesson_with_blocks(lesson_id: int) -> dict | None:
    lesson = get_lesson(lesson_id)
    if lesson is None:
        return None
    lesson["blocks"] = list_lesson_blocks(lesson_id)
    return lesson


def assignment_has_lessons(assignment_id: int) -> bool:
    row = db.query_one(
        "SELECT COUNT(*) AS c FROM lessons WHERE assignment_id = ?", (assignment_id,)
    )
    return (row["c"] if row else 0) > 0


# --- answers (student's own work) ---
def get_answer_for_block(block_id: int) -> dict | None:
    return db.row_to_dict(db.query_one(
        "SELECT * FROM lesson_answers WHERE lesson_block_id = ?", (block_id,)
    ))


def save_answer_for_block(block_id: int, assignment_id: int, content: str) -> int:
    existing = get_answer_for_block(block_id)
    if existing:
        db.execute(
            "UPDATE lesson_answers SET content_text = ?, updated_at = datetime('now') WHERE id = ?",
            (content, existing["id"]),
        )
        return existing["id"]
    return db.execute(
        "INSERT INTO lesson_answers (lesson_block_id, assignment_id, content_text) VALUES (?, ?, ?)",
        (block_id, assignment_id, content),
    )


def list_answerable_blocks(assignment_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT lb.id AS block_id, lb.type, lb.payload_json, "
        "l.id AS lesson_id, l.seq AS lesson_seq, l.title AS lesson_title "
        "FROM lesson_blocks lb JOIN lessons l ON l.id = lb.lesson_id "
        "WHERE l.assignment_id = ? AND lb.type IN ('scaffold_q','draft') "
        "ORDER BY l.seq, lb.seq",
        (assignment_id,),
    ))


# --- tutor transcript ---
def list_tutor_messages(lesson_id: int, user_id: int | None) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT id, role, content, created_at FROM tutor_messages "
        "WHERE lesson_id = ? AND (user_id IS ? OR user_id = ?) ORDER BY id",
        (lesson_id, user_id, user_id),
    ))


def insert_tutor_message(lesson_id: int, user_id: int | None, role: str, content: str) -> int:
    return db.execute(
        "INSERT INTO tutor_messages (lesson_id, user_id, role, content) VALUES (?, ?, ?, ?)",
        (lesson_id, user_id, role, content),
    )


def delete_tutor_messages(lesson_id: int, user_id: int | None) -> int:
    conn = db.connect()
    cur = conn.execute(
        "DELETE FROM tutor_messages WHERE lesson_id = ? AND (user_id IS ? OR user_id = ?)",
        (lesson_id, user_id, user_id),
    )
    conn.commit()
    return cur.rowcount


# --- gamification (XP) ---
def get_user_xp(user_id: int) -> dict | None:
    return db.row_to_dict(db.query_one("SELECT * FROM user_xp WHERE user_id = ?", (user_id,)))


def ensure_user_xp(user_id: int, daily_goal: int) -> dict:
    row = get_user_xp(user_id)
    if row is None:
        db.execute(
            "INSERT INTO user_xp (user_id, total_xp, daily_goal) VALUES (?, 0, ?)",
            (user_id, daily_goal),
        )
        row = get_user_xp(user_id)
    return row


def add_user_xp(user_id: int, xp: int) -> None:
    db.execute(
        "UPDATE user_xp SET total_xp = total_xp + ?, updated_at = datetime('now') WHERE user_id = ?",
        (xp, user_id),
    )


def get_xp_event(user_id: int | None, lesson_id: int, stage_key: str) -> dict | None:
    return db.row_to_dict(db.query_one(
        "SELECT * FROM xp_events WHERE (user_id IS ? OR user_id = ?) AND lesson_id = ? AND stage_key = ?",
        (user_id, user_id, lesson_id, stage_key),
    ))


def insert_xp_event(user_id: int | None, lesson_id: int, stage_key: str, xp: int, date: str) -> int:
    return db.execute(
        "INSERT INTO xp_events (user_id, lesson_id, stage_key, xp, date) VALUES (?, ?, ?, ?, ?)",
        (user_id, lesson_id, stage_key, xp, date),
    )


def completed_stage_keys(user_id: int | None, lesson_id: int) -> set[str]:
    rows = db.query_all(
        "SELECT stage_key FROM xp_events WHERE (user_id IS ? OR user_id = ?) AND lesson_id = ?",
        (user_id, user_id, lesson_id),
    )
    return {r["stage_key"] for r in rows}


def xp_earned_on(user_id: int | None, date: str) -> int:
    row = db.query_one(
        "SELECT COALESCE(SUM(xp), 0) AS s FROM xp_events "
        "WHERE (user_id IS ? OR user_id = ?) AND date = ?",
        (user_id, user_id, date),
    )
    return row["s"] if row else 0


# --- lesson streak ---
def get_lesson_streak(date: str) -> dict | None:
    return db.row_to_dict(db.query_one(
        "SELECT * FROM lesson_streak WHERE date = ?", (date,)
    ))


def bump_lesson_streak(date: str) -> None:
    db.execute(
        "INSERT INTO lesson_streak (date, completed_count) VALUES (?, 1) "
        "ON CONFLICT(date) DO UPDATE SET completed_count = completed_count + 1",
        (date,),
    )


# --- planner ---
def list_todo_lessons_for_user(user_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT l.id AS lesson_id, l.title, l.est_minutes, l.status, l.seq, "
        "a.id AS assignment_id, a.title AS assignment, a.due_at "
        "FROM lessons l JOIN assignments a ON a.id = l.assignment_id "
        "JOIN courses c ON c.id = a.course_id "
        "JOIN enrollments e ON e.course_id = c.id AND e.user_id = ? "
        "WHERE l.status = 'todo' "
        "ORDER BY a.due_at IS NULL, a.due_at, l.seq",
        (user_id,),
    ))


def list_scheduled_lessons_for_user(user_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT pe.scheduled_date AS date, l.id AS lesson_id, l.title, l.est_minutes, "
        "l.status, l.seq, a.title AS assignment, a.due_at "
        "FROM plan_entries pe JOIN lessons l ON l.id = pe.lesson_id "
        "JOIN assignments a ON a.id = l.assignment_id JOIN courses c ON c.id = a.course_id "
        "JOIN enrollments e ON e.course_id = c.id AND e.user_id = ? "
        "ORDER BY pe.scheduled_date, l.seq",
        (user_id,),
    ))


def list_backlog_lessons_for_user(user_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT l.id AS lesson_id, l.title, l.est_minutes, l.seq, "
        "a.title AS assignment, a.due_at "
        "FROM lessons l JOIN assignments a ON a.id = l.assignment_id "
        "JOIN courses c ON c.id = a.course_id "
        "JOIN enrollments e ON e.course_id = c.id AND e.user_id = ? "
        "WHERE l.status = 'todo' AND l.id NOT IN (SELECT lesson_id FROM plan_entries) "
        "ORDER BY a.due_at IS NULL, a.due_at, l.seq",
        (user_id,),
    ))


def get_lesson_for_user(user_id: int, lesson_id: int) -> dict | None:
    return db.row_to_dict(db.query_one(
        "SELECT l.id AS lesson_id, l.est_minutes, a.due_at "
        "FROM lessons l JOIN assignments a ON a.id = l.assignment_id "
        "JOIN courses c ON c.id = a.course_id "
        "JOIN enrollments e ON e.course_id = c.id AND e.user_id = ? "
        "WHERE l.id = ?",
        (user_id, lesson_id),
    ))


def clear_plan_entry(lesson_id: int) -> int:
    conn = db.connect()
    cur = conn.execute("DELETE FROM plan_entries WHERE lesson_id = ?", (lesson_id,))
    conn.commit()
    return cur.rowcount


def insert_plan_entry(lesson_id: int, scheduled_date: str, reflow_version: int) -> int:
    return db.execute(
        "INSERT INTO plan_entries (lesson_id, scheduled_date, reflow_version) VALUES (?, ?, ?)",
        (lesson_id, scheduled_date, reflow_version),
    )


def max_reflow_version() -> int:
    row = db.query_one("SELECT MAX(reflow_version) AS v FROM plan_entries")
    return (row["v"] if row and row["v"] is not None else 0)


def current_day_loads_for_user(user_id: int) -> dict[str, int]:
    rows = db.query_all(
        "SELECT pe.scheduled_date AS d, SUM(l.est_minutes) AS m "
        "FROM plan_entries pe JOIN lessons l ON l.id = pe.lesson_id "
        "JOIN assignments a ON a.id = l.assignment_id JOIN courses c ON c.id = a.course_id "
        "JOIN enrollments e ON e.course_id = c.id AND e.user_id = ? "
        "GROUP BY pe.scheduled_date",
        (user_id,),
    )
    return {r["d"]: (r["m"] or 0) for r in rows}


def clear_plan_for_user(user_id: int) -> int:
    conn = db.connect()
    cur = conn.execute(
        "DELETE FROM plan_entries WHERE lesson_id IN ("
        "SELECT l.id FROM lessons l JOIN assignments a ON a.id = l.assignment_id "
        "JOIN courses c ON c.id = a.course_id "
        "JOIN enrollments e ON e.course_id = c.id AND e.user_id = ?)",
        (user_id,),
    )
    conn.commit()
    return cur.rowcount


# --- submission consent ---
def latest_consent(assignment_id: int, user_id: int | None) -> dict | None:
    return db.row_to_dict(db.query_one(
        "SELECT * FROM submission_consent WHERE assignment_id = ? "
        "AND (user_id IS ? OR user_id = ?) ORDER BY id DESC LIMIT 1",
        (assignment_id, user_id, user_id),
    ))


def insert_consent(assignment_id: int, user_id: int | None, content_hash: str,
                   reviewed: int, consented: int) -> int:
    return db.execute(
        "INSERT INTO submission_consent (assignment_id, user_id, content_hash, reviewed, consented) "
        "VALUES (?, ?, ?, ?, ?)",
        (assignment_id, user_id, content_hash, reviewed, consented),
    )


# --- learning preferences ---
def get_learning_preferences(user_id: int) -> dict | None:
    return db.row_to_dict(db.query_one(
        "SELECT * FROM learning_preferences WHERE user_id = ?", (user_id,)
    ))


def upsert_learning_preferences(user_id: int, learning_styles: str, learning_notes: str) -> None:
    db.execute(
        "INSERT INTO learning_preferences (user_id, learning_styles, learning_notes) "
        "VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
        "learning_styles = excluded.learning_styles, "
        "learning_notes = excluded.learning_notes, updated_at = datetime('now')",
        (user_id, learning_styles, learning_notes),
    )


# --- resource cache ---
def cache_get(provider: str, request_hash: str) -> dict | None:
    row = db.query_one(
        "SELECT response_json FROM resource_cache WHERE provider = ? AND request_hash = ?",
        (provider, request_hash),
    )
    return json.loads(row["response_json"]) if row else None


def cache_set(provider: str, request_hash: str, data: Any) -> None:
    db.execute(
        "INSERT OR REPLACE INTO resource_cache (provider, request_hash, response_json) "
        "VALUES (?, ?, ?)",
        (provider, request_hash, json.dumps(data)),
    )


# ------------------------------ portfolio ----------------------------------
# Honesty-by-design reads: a student's COMPLETED work is any assignment with at
# least one 'done' lesson, scoped to the courses they're enrolled in. Mirrors
# the 'done'-lesson basis compile uses — nothing is credited that the student
# didn't actually finish.
def list_completed_work_for_user(user_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT DISTINCT a.id, a.title, a.description, a.due_at, c.code AS course_code, "
        "c.title AS course_title "
        "FROM assignments a JOIN courses c ON c.id = a.course_id "
        "JOIN enrollments e ON e.course_id = c.id AND e.user_id = ? "
        "JOIN lessons l ON l.assignment_id = a.id "
        "WHERE l.status = 'done' ORDER BY a.id",
        (user_id,),
    ))


def list_completed_lesson_titles(assignment_id: int) -> list[str]:
    rows = db.query_all(
        "SELECT title FROM lessons WHERE assignment_id = ? AND status = 'done' ORDER BY seq",
        (assignment_id,),
    )
    return [r["title"] for r in rows]


def list_completed_courses_for_user(user_id: int) -> list[str]:
    rows = db.query_all(
        "SELECT DISTINCT c.code, c.title FROM courses c "
        "JOIN enrollments e ON e.course_id = c.id AND e.user_id = ? "
        "JOIN assignments a ON a.course_id = c.id "
        "JOIN lessons l ON l.assignment_id = a.id "
        "WHERE l.status = 'done' ORDER BY c.code",
        (user_id,),
    )
    return [f"{r['code']} — {r['title']}" for r in rows]


# --- user_skill (persisted, accumulating) ---
def list_user_skills(user_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT skill, source, evidence, created_at FROM user_skill "
        "WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ))


def upsert_user_skill(user_id: int, skill: str, source: str, evidence: str) -> None:
    db.execute(
        "INSERT INTO user_skill (user_id, skill, source, evidence) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, skill) DO UPDATE SET "
        "evidence = CASE WHEN excluded.evidence <> '' THEN excluded.evidence "
        "ELSE user_skill.evidence END",
        (user_id, skill, source, evidence),
    )


# --- portfolio_project (accepted projects) ---
def create_portfolio_project(user_id: int, name: str, difficulty: str | None,
                             spec_json: str, status: str = "recommended") -> int:
    return db.execute(
        "INSERT INTO portfolio_project (user_id, name, difficulty, spec_json, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, name, difficulty, spec_json, status),
    )


def get_portfolio_project(project_id: int, user_id: int) -> dict | None:
    return db.row_to_dict(db.query_one(
        "SELECT * FROM portfolio_project WHERE id = ? AND user_id = ?",
        (project_id, user_id),
    ))


def get_portfolio_project_by_name(user_id: int, name: str) -> dict | None:
    return db.row_to_dict(db.query_one(
        "SELECT * FROM portfolio_project WHERE user_id = ? AND name = ? "
        "ORDER BY id DESC LIMIT 1",
        (user_id, name),
    ))


def list_portfolio_projects(user_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT id, name, difficulty, spec_json, status, assignment_id, created_at "
        "FROM portfolio_project WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ))


def link_portfolio_project_assignment(project_id: int, assignment_id: int) -> None:
    db.execute(
        "UPDATE portfolio_project SET assignment_id = ?, status = 'in_progress', "
        "updated_at = datetime('now') WHERE id = ?",
        (assignment_id, project_id),
    )


def set_portfolio_project_status(user_id: int, project_id: int, status: str) -> int:
    conn = db.connect()
    cur = conn.execute(
        "UPDATE portfolio_project SET status = ?, updated_at = datetime('now') "
        "WHERE id = ? AND user_id = ?",
        (status, project_id, user_id),
    )
    conn.commit()
    return cur.rowcount


# --- self-assigned "Portfolio projects" course helpers ---
# The staged flow is reached through the normal course-scoped endpoints, which
# require the acting student to be enrolled. So each student gets a private
# "Portfolio projects" course they are enrolled in, and project assignments live
# under it. Section is namespaced per-user to keep it private + unique.
def get_portfolio_course_for_user(user_id: int) -> dict | None:
    return db.row_to_dict(db.query_one(
        "SELECT * FROM courses WHERE code = 'PORTFOLIO' AND section = ?",
        (f"u{user_id}",),
    ))


def list_assignment_lessons_brief(assignment_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT id, seq, title, status FROM lessons WHERE assignment_id = ? ORDER BY seq",
        (assignment_id,),
    ))


# ------------------------------- forums ------------------------------------
def create_thread(course_id: int, author_id: int, title: str, body: str) -> int:
    return db.execute(
        "INSERT INTO forum_threads (course_id, author_id, title, body) VALUES (?, ?, ?, ?)",
        (course_id, author_id, title, body),
    )


def get_thread(thread_id: int) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM forum_threads WHERE id = ?", (thread_id,))
    )


def list_threads(course_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT * FROM forum_threads WHERE course_id = ? "
        "ORDER BY pinned DESC, created_at DESC",
        (course_id,),
    ))


def create_post(thread_id: int, author_id: int, body: str) -> int:
    return db.execute(
        "INSERT INTO forum_posts (thread_id, author_id, body) VALUES (?, ?, ?)",
        (thread_id, author_id, body),
    )


def list_posts(thread_id: int, include_hidden: bool) -> list[dict]:
    if include_hidden:
        rows = db.query_all(
            "SELECT * FROM forum_posts WHERE thread_id = ? ORDER BY created_at",
            (thread_id,),
        )
    else:
        rows = db.query_all(
            "SELECT * FROM forum_posts WHERE thread_id = ? AND hidden = 0 ORDER BY created_at",
            (thread_id,),
        )
    return db.rows_to_dicts(rows)


def get_post(post_id: int) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM forum_posts WHERE id = ?", (post_id,))
    )


def set_post_hidden(post_id: int, hidden: bool) -> None:
    db.execute("UPDATE forum_posts SET hidden = ? WHERE id = ?", (1 if hidden else 0, post_id))


# ------------------------------ projects -----------------------------------
def create_project(**kw: Any) -> int:
    return db.execute(
        "INSERT INTO projects (project_type, title, description, course_id, owner_id, "
        "repo_url, demo_url, tech_stack, published) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (kw["project_type"], kw["title"], kw.get("description", ""),
         kw.get("course_id"), kw.get("owner_id"), kw.get("repo_url"),
         kw.get("demo_url"), kw.get("tech_stack"), 1 if kw.get("published") else 0),
    )


def get_project(project_id: int) -> dict | None:
    return db.row_to_dict(
        db.query_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    )


def list_guided_projects(course_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT * FROM projects WHERE project_type = 'guided' AND course_id = ?",
        (course_id,),
    ))


def list_showcase_projects() -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT * FROM projects WHERE project_type = 'showcase' AND published = 1 "
        "ORDER BY created_at DESC"
    ))


def create_project_comment(project_id: int, author_id: int, body: str) -> int:
    return db.execute(
        "INSERT INTO project_comments (project_id, author_id, body) VALUES (?, ?, ?)",
        (project_id, author_id, body),
    )


def list_project_comments(project_id: int) -> list[dict]:
    return db.rows_to_dicts(db.query_all(
        "SELECT * FROM project_comments WHERE project_id = ? ORDER BY created_at",
        (project_id,),
    ))


# ---------------------------- announcements --------------------------------
def create_announcement(**kw: Any) -> int:
    return db.execute(
        "INSERT INTO announcements (course_id, author_id, title, body, category, location, event_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (kw.get("course_id"), kw["author_id"], kw["title"], kw.get("body", ""),
         kw.get("category", "event"), kw.get("location"), kw.get("event_at")),
    )


def list_announcements_for_user(course_ids: list[int], is_admin: bool) -> list[dict]:
    if is_admin:
        return db.rows_to_dicts(db.query_all(
            "SELECT * FROM announcements ORDER BY created_at DESC"
        ))
    if course_ids:
        placeholders = ", ".join("?" for _ in course_ids)
        sql = (
            f"SELECT * FROM announcements WHERE course_id IS NULL "
            f"OR course_id IN ({placeholders}) ORDER BY created_at DESC"
        )
        return db.rows_to_dicts(db.query_all(sql, course_ids))
    return db.rows_to_dicts(db.query_all(
        "SELECT * FROM announcements WHERE course_id IS NULL ORDER BY created_at DESC"
    ))
