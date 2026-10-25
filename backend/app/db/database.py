"""SQLite data-access layer (standard library only).

All SQL lives behind this module so the storage engine can be swapped to
MySQL on the Ubuntu VM (per the PRD) by replacing `connect()` and adjusting
the DDL dialect. See docs/MIGRATION.md.
"""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from contextlib import contextmanager
from typing import Any

from ..core.config import settings

_local = threading.local()

# ---------------------------------------------------------------------------
# Schema. Written to be close to MySQL-compatible; AUTOINCREMENT/INTEGER
# PRIMARY KEY maps to MySQL AUTO_INCREMENT, TEXT->TEXT/VARCHAR, etc.
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    hashed_password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student',
    org_verified INTEGER NOT NULL DEFAULT 0,
    osu_name_dot_number TEXT,
    bio TEXT,
    avatar_url TEXT,
    github_url TEXT,
    linkedin_url TEXT,
    major TEXT,
    grad_year INTEGER,
    company TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS registered_recruiters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    company TEXT NOT NULL,
    added_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canvas_course_id TEXT,
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    section TEXT NOT NULL,
    term TEXT NOT NULL DEFAULT 'AU25',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'student',
    UNIQUE(user_id, course_id)
);

CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    canvas_assignment_id TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'assignment',
    due_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =====================================================================
-- Lesson engine (ported from the JS lesson engine). REPLACES the old
-- static mini_lessons / lesson_steps (concept/tip/quiz) model with the
-- interactive decompose -> Coach tutor -> gamified staged flow -> compile
-- experience. All of these hang off the existing `assignments` table.
-- =====================================================================

-- An assignment is decomposed into an ordered sequence of ~10-15 min lessons.
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    title TEXT NOT NULL,
    est_minutes INTEGER NOT NULL DEFAULT 12,
    status TEXT NOT NULL DEFAULT 'todo',  -- todo | done
    generated_by TEXT NOT NULL DEFAULT 'mock',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Each lesson is a sequence of typed blocks (the raw material the staged
-- flow is DERIVED from): video | excerpt | scaffold_q | draft | flashcards.
CREATE TABLE IF NOT EXISTS lesson_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    type TEXT NOT NULL,          -- video | excerpt | scaffold_q | draft | flashcards
    payload_json TEXT NOT NULL   -- type-specific payload (JSON)
);

-- The student's OWN writing for a scaffold_q / draft block. Compile reads
-- only this table (honesty-by-design: it never invents content).
CREATE TABLE IF NOT EXISTS lesson_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_block_id INTEGER NOT NULL UNIQUE REFERENCES lesson_blocks(id) ON DELETE CASCADE,
    assignment_id INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    content_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Interactive "Coach" tutor transcript. One logical session per
-- (lesson_id, user_id); rows are the transcript, oldest-first by id.
CREATE TABLE IF NOT EXISTS tutor_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,          -- user | model
    content TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Gamification: per-user running XP total + their daily XP goal.
CREATE TABLE IF NOT EXISTS user_xp (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    total_xp INTEGER NOT NULL DEFAULT 0,
    daily_goal INTEGER NOT NULL DEFAULT 50,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- XP ledger AND stage-progress record in one. A row means "this user
-- completed this stage of this lesson and earned its XP". The UNIQUE
-- constraint makes awarding idempotent (re-doing a stage never double-counts).
CREATE TABLE IF NOT EXISTS xp_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE,
    stage_key TEXT NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    date TEXT NOT NULL,          -- YYYY-MM-DD the XP was earned
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, lesson_id, stage_key)
);

-- Daily completed-lesson streak counter (shared across users; mirrors the
-- JS engine's single-table streak).
CREATE TABLE IF NOT EXISTS lesson_streak (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,   -- YYYY-MM-DD
    completed_count INTEGER NOT NULL DEFAULT 0
);

-- Planner: a lesson scheduled onto a specific day (anti-procrastination).
CREATE TABLE IF NOT EXISTS plan_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    scheduled_date TEXT NOT NULL,  -- YYYY-MM-DD
    reflow_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Submission review + consent. Consent is tied to a content_hash of the
-- exact compiled text approved, so editing an answer invalidates it.
CREATE TABLE IF NOT EXISTS submission_consent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    reviewed INTEGER NOT NULL DEFAULT 0,
    consented INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Per-user learning-style preferences (max 2 styles + free-text notes) used
-- to tailor the AI. Separate from the users table so it stays additive.
CREATE TABLE IF NOT EXISTS learning_preferences (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    learning_styles TEXT NOT NULL DEFAULT '[]',  -- JSON array (visual|auditory|reading|kinesthetic)
    learning_notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Cache for keyed external resource lookups (YouTube / Wikipedia / Gemini
-- JSON) — demo-safety so a later live failure can serve a cached response.
CREATE TABLE IF NOT EXISTS resource_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    request_hash TEXT NOT NULL UNIQUE,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_lessons_assignment ON lessons(assignment_id);
CREATE INDEX IF NOT EXISTS idx_blocks_lesson ON lesson_blocks(lesson_id);
CREATE INDEX IF NOT EXISTS idx_answers_assignment ON lesson_answers(assignment_id);
CREATE INDEX IF NOT EXISTS idx_tutor_lesson_user ON tutor_messages(lesson_id, user_id, id);
CREATE INDEX IF NOT EXISTS idx_xp_user_lesson ON xp_events(user_id, lesson_id);
CREATE INDEX IF NOT EXISTS idx_xp_user_date ON xp_events(user_id, date);
CREATE INDEX IF NOT EXISTS idx_plan_lesson ON plan_entries(lesson_id);
CREATE INDEX IF NOT EXISTS idx_consent_assignment ON submission_consent(assignment_id, user_id, id);

CREATE TABLE IF NOT EXISTS forum_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    pinned INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS forum_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES forum_threads(id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    hidden INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    repo_url TEXT,
    demo_url TEXT,
    tech_stack TEXT,
    published INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'event',
    location TEXT,
    event_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect() -> sqlite3.Connection:
    """Return a thread-local connection with row access by column name."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _local.conn = conn
    return conn


def init_db() -> None:
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ----------------------------- query helpers -------------------------------
def query_all(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return connect().execute(sql, tuple(params)).fetchall()


def query_one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return connect().execute(sql, tuple(params)).fetchone()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Execute a write and return lastrowid."""
    conn = connect()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur.lastrowid


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]
