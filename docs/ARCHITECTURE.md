# Learn++ Architecture

## Overview

Learn++ is a single-origin web application: one process serves both the JSON
API (`/api/*`) and the static SPA (everything else). This matches the PRD's
"backend on the VM, UI on localhost" model while keeping deployment trivial.

```
Browser (SPA)  ──HTTP──▶  Learn++ server  ──▶  SQLite (SQLite→MySQL on VM)
                              │
                              ├─▶ GeminiService      (mini-lesson generation)
                              ├─▶ CanvasScraper       (Playwright, courses/calendar/members)
                              ├─▶ OSUAuth             (identity verify + 2FA)
                              └─▶ OSUClassSearch      (schedule advisor)
```

Every integration has a **real implementation path** (used on the VM with
internet + credentials) and an **offline mock** (used in dev/CI) selected by
`USE_MOCK_INTEGRATIONS`, which auto-enables when no `GEMINI_API_KEY` is set.

## Backend layers

- **core/** — `config` (env-driven settings) and `security` (PBKDF2 password
  hashing + a standard-library HS256 JWT implementation).
- **db/** — `database` owns the SQLite connection, schema DDL, and tiny
  query helpers; `repository` holds every SQL statement behind named
  functions. All persistence flows through here, so swapping to MySQL touches
  only these two files.
- **integrations/** — external services, each mockable.
- **services/** — business logic: `lesson_service` (the "auto-generate lessons
  for everything due within 7 days" job) and `onboarding_service` (the Canvas
  scrape → persist → enroll flow).
- **web/** — `framework` (a ~100-line path-pattern router over
  `http.server`, with JSON + bearer-token auth), `access` (course/role
  guards), and `routes` (all endpoints).
- **main.py** — wires the router and static file serving into a
  `ThreadingHTTPServer`.

## Why standard-library only?

The build targets an isolated environment with no package index access, so the
backend deliberately avoids third-party runtime dependencies. This keeps the
app runnable and verifiable anywhere Python 3.10+ exists, including the Ubuntu
VM, with zero `pip install`. The optional production extras (PyMySQL for MySQL,
Playwright for Canvas) are isolated to the integration/DB boundary.

## Access-control model (PRD Success Criteria)

| Actor | Can see |
|---|---|
| Student | Only their enrolled courses, those forums, course assignments/lessons, guided projects for their courses, the showcase, org + their-course announcements, the advisor, their profile. |
| Professor | Only their own courses + ability to moderate posts and post announcements **in their own courses only**. |
| Admin | Everything, plus the recruiter registry. |
| Recruiter | **Only** the published project showcase + comments — never courses, forums, or the advisor. Account creation requires being on the authorized registry. |

Guards live in `web/access.py` (`require_course_access`,
`require_course_instructor`) and `Request.require_roles()` in
`web/framework.py`. These are unit-exercised by `scripts/smoke_test.py`.

## Auth flow

1. Login page offers 4 roles. The selected role must match the stored account
   role (prevents privilege confusion).
2. Students/professors: credentials verified → OSU two-factor challenge →
   token. (Offline, the 2FA code is `000000`.)
3. Recruiters/admins: credentials verified → token.
4. On student **signup**, the Canvas onboarding job runs: scrape courses +
   calendar + members, persist, enroll the student, link known professors, then
   auto-generate mini-lessons for everything due within 7 days.

## Data model

`users`, `registered_recruiters`, `courses`, `enrollments`, `assignments`,
`mini_lessons`, `lesson_steps`, `forum_threads`, `forum_posts`, `projects`,
`project_comments`, `announcements`. Full DDL in `backend/app/db/database.py`.
