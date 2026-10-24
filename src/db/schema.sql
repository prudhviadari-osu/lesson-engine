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

-- Interactive tutor conversation (prototype). One logical "session" per
-- (lesson_id, user_id): a multi-turn chat where the student and Gemini go back
-- and forth. Rows are the transcript, oldest-first by id. role is 'user'
-- (the student) or 'model' (the tutor). Rebuild the DB (npm run seed) to add it.
CREATE TABLE IF NOT EXISTS tutor_message (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  lesson_id     INTEGER NOT NULL REFERENCES lesson(id) ON DELETE CASCADE,
  user_id       INTEGER REFERENCES user(id) ON DELETE CASCADE,
  role          TEXT NOT NULL,       -- user | model
  content       TEXT NOT NULL DEFAULT '',
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tutor_lesson_user ON tutor_message(lesson_id, user_id, id);

-- Gamification (staged lesson flow). ADDITIVE tables — no changes to existing
-- ones (SQLite can't add columns via CREATE IF NOT EXISTS, so prefer new tables).
-- Rebuild the DB (npm run seed) after pulling these to pick them up.

-- Per-user running XP total + their daily XP goal. One row per user; created
-- lazily on first award (see services/flow.js). daily_goal defaults to 50.
CREATE TABLE IF NOT EXISTS user_xp (
  user_id     INTEGER PRIMARY KEY REFERENCES user(id) ON DELETE CASCADE,
  total_xp    INTEGER NOT NULL DEFAULT 0,
  daily_goal  INTEGER NOT NULL DEFAULT 50,
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- XP ledger AND stage-progress record in one. A row here means "this user has
-- completed this stage of this lesson and earned its XP". stage_key is a stable
-- derived id like 'intro', 'video:14', 'challenge:9', 'draft:12', 'complete'.
-- UNIQUE(user_id, lesson_id, stage_key) makes awarding idempotent (re-doing a
-- stage never double-counts XP). `date` (YYYY-MM-DD) powers the daily-goal meter.
CREATE TABLE IF NOT EXISTS xp_event (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER REFERENCES user(id) ON DELETE CASCADE,
  lesson_id   INTEGER REFERENCES lesson(id) ON DELETE CASCADE,
  stage_key   TEXT NOT NULL,
  xp          INTEGER NOT NULL DEFAULT 0,
  date        TEXT NOT NULL,            -- YYYY-MM-DD (local day the XP was earned)
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(user_id, lesson_id, stage_key)
);

CREATE INDEX IF NOT EXISTS idx_xp_event_user_lesson ON xp_event(user_id, lesson_id);
CREATE INDEX IF NOT EXISTS idx_xp_event_user_date   ON xp_event(user_id, date);

-- Submission review + consent (SPEC §5 honesty boundary). Before a compiled
-- submission is considered "ready", the student must explicitly review it and
-- give consent. We record a snapshot of exactly what they consented to, so
-- consent is tied to that specific content (editing an answer invalidates it).
CREATE TABLE IF NOT EXISTS submission_consent (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  assignment_id  INTEGER NOT NULL REFERENCES assignment(id) ON DELETE CASCADE,
  user_id        INTEGER REFERENCES user(id) ON DELETE CASCADE,
  content_hash   TEXT NOT NULL,   -- hash of the compiled text they approved
  reviewed       INTEGER NOT NULL DEFAULT 0, -- 1 = "I reviewed this"
  consented      INTEGER NOT NULL DEFAULT 0, -- 1 = "this is my own work, submit it"
  created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_consent_assignment ON submission_consent(assignment_id, user_id, id);

CREATE INDEX IF NOT EXISTS idx_course_user       ON course(user_id);
CREATE INDEX IF NOT EXISTS idx_assignment_course ON assignment(course_id);
CREATE INDEX IF NOT EXISTS idx_lesson_assignment ON lesson(assignment_id);
CREATE INDEX IF NOT EXISTS idx_block_lesson       ON lesson_block(lesson_id);
CREATE INDEX IF NOT EXISTS idx_answer_assignment  ON answer(assignment_id);
CREATE INDEX IF NOT EXISTS idx_plan_lesson        ON plan_entry(lesson_id);
