-- learning++ schema (SPEC §5)
-- SQLite via better-sqlite3

PRAGMA foreign_keys = ON;

-- Lightweight "profiles" (no passwords for the hackathon; real auth = v2).
-- Learning preferences live here since they are per-user.
CREATE TABLE IF NOT EXISTS user (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  display_name    TEXT NOT NULL,
  learning_styles TEXT NOT NULL DEFAULT '[]', -- JSON array, 1-2 of: visual|auditory|reading|kinesthetic
  learning_notes  TEXT NOT NULL DEFAULT '',   -- free-text "anything specific?"
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS course (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER REFERENCES user(id) ON DELETE CASCADE,
  canvas_id   TEXT,
  name        TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assignment (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  course_id         INTEGER NOT NULL REFERENCES course(id) ON DELETE CASCADE,
  canvas_id         TEXT,
  title             TEXT NOT NULL,
  description_html  TEXT,
  description_text  TEXT,
  due_at            TEXT,                 -- ISO8601
  points            REAL,
  submission_type   TEXT,                 -- online_text_entry | online_upload | online_url | external_tool
  source            TEXT NOT NULL DEFAULT 'paste',  -- api | playwright | paste
  status            TEXT NOT NULL DEFAULT 'ingested', -- ingested | decomposed | in_progress | compiled
  created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS attachment (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  assignment_id  INTEGER NOT NULL REFERENCES assignment(id) ON DELETE CASCADE,
  filename       TEXT NOT NULL,
  local_path     TEXT,
  mime           TEXT,
  kind           TEXT NOT NULL DEFAULT 'canvas_file' -- canvas_file | uploaded_textbook
);

CREATE TABLE IF NOT EXISTS lesson (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  assignment_id  INTEGER NOT NULL REFERENCES assignment(id) ON DELETE CASCADE,
  seq            INTEGER NOT NULL,
  title          TEXT NOT NULL,
  est_minutes    INTEGER NOT NULL DEFAULT 12,
  status         TEXT NOT NULL DEFAULT 'todo', -- todo | done
  created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lesson_block (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  lesson_id     INTEGER NOT NULL REFERENCES lesson(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  type          TEXT NOT NULL,       -- video | excerpt | scaffold_q | draft | flashcards
  payload_json  TEXT NOT NULL        -- type-specific (SPEC §6)
);

CREATE TABLE IF NOT EXISTS answer (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  lesson_block_id INTEGER NOT NULL REFERENCES lesson_block(id) ON DELETE CASCADE,
  assignment_id   INTEGER NOT NULL REFERENCES assignment(id) ON DELETE CASCADE,
  content_text    TEXT NOT NULL DEFAULT '',
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resource_cache (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  provider      TEXT NOT NULL,       -- youtube | gemini
  request_hash  TEXT NOT NULL UNIQUE,
  response_json TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS plan_entry (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  lesson_id       INTEGER NOT NULL REFERENCES lesson(id) ON DELETE CASCADE,
  scheduled_date  TEXT NOT NULL,     -- YYYY-MM-DD
  reflow_version  INTEGER NOT NULL DEFAULT 1,
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS streak (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  date            TEXT NOT NULL UNIQUE,  -- YYYY-MM-DD
  completed_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_course_user       ON course(user_id);
CREATE INDEX IF NOT EXISTS idx_assignment_course ON assignment(course_id);
CREATE INDEX IF NOT EXISTS idx_lesson_assignment ON lesson(assignment_id);
CREATE INDEX IF NOT EXISTS idx_block_lesson       ON lesson_block(lesson_id);
CREATE INDEX IF NOT EXISTS idx_answer_assignment  ON answer(assignment_id);
CREATE INDEX IF NOT EXISTS idx_plan_lesson        ON plan_entry(lesson_id);
