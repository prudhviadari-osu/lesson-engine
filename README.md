Repository for the **HACK OH/IO** project — **Learn++**.

---

# Learn++

> Learn the assignment, don't just finish it.

Learn++ is a web tool for college students (built around **The Ohio State
University**) that turns upcoming coursework into an **interactive, gamified
lesson experience** — an AI "Coach" tutor plus a staged flow that teaches the
concept, then guides you to produce the real deliverable **in your own words**
(the opposite of copy-pasting an AI answer). It also hosts **course-scoped
forums**, a **project showcase** that approved recruiters can browse,
**announcements**, a **schedule advisor**, **customizable profiles**, a
**study planner**, and a **Portfolio** builder — all under role-based access
control for Students, Professors, Administration, and Verified Recruiters.

This is **one unified Python app** (standard-library only, runs fully offline).
It merges a teammate's Learn++ platform (auth/roles/forums/recruiters/
announcements/advisor/profiles/Canvas-scrape) with a ported **lesson engine**
(decompose → Coach tutor → gamified staged flow → planner/reflow → compile with
a review+consent gate → learning-style preferences).

### The lesson experience

1. **Decompose** — an assignment is broken into ~10-15 min lessons, each a
   sequence of typed blocks (video / reading excerpt / scaffold question /
   draft / flashcards). Tailored by the student's learning-style preferences.
2. **Staged flow** (the main way a lesson is "done") — an ordered journey
   `intro → watch video → read excerpt → bite-size challenges → draft the real
   deliverable → complete`, with **XP per stage, a lesson progress %, a daily
   XP goal, and a streak**. Instant correct/try-again feedback on challenges.
3. **Coach tutor** — a live multi-turn chat that teaches in small bites, reacts
   to what you actually typed, and **never writes your answer for you**.
4. **Compile + consent** — assembles your own answers into a submission bundle,
   grouped by lesson, and gates "ready to submit" behind an explicit
   review+consent tied to a content hash (editing an answer makes it stale).
5. **Planner** — schedules lessons backward from each due date with a daily cap
   and submission buffer; unschedule → backlog.
6. **Portfolio** (the point of uniqueness) — from the work you've actually
   completed, AI extracts resume-worthy **skills** (accumulating over time) and
   recommends **portfolio projects** that build on them. "Get Help" on a project
   materializes it as a self-assigned assignment run through the *same* gamified
   lesson flow — so a recommendation becomes a real, playable lesson, not a
   static plan. A resume-friendly **Personal Portfolio** view shows your skills,
   completed work, saved projects, and stats. Skills are only credited from work
   you genuinely finished (same honesty basis as compile).

**Mock vs real:** with **no `GEMINI_API_KEY`** (or `USE_MOCK_INTEGRATIONS=1`)
every AI path — decompose, Coach tutor, and per-stage feedback — uses
deterministic offline mocks, so the whole app and smoke test run with no
network. Set `GEMINI_API_KEY` to use the real Gemini REST API (urllib, zero
pip installs); it falls back to the mock on overload/error so work is never
lost.

---

## Quick start

No third-party packages are required — the backend runs on the Python standard
library, and the database is SQLite out of the box.

```bash
# 1. Seed the database with sample users + content
python -m backend.scripts.seed

# 2. Start the server (serves API + UI on one origin)
python -m backend.app.main

# 3. Open the UI
#    http://127.0.0.1:8000
```

> Requires Python 3.10+ (tested on 3.11).

### Demo accounts

All seeded accounts use the password **`Password123`**.
Students & professors complete OSU two-factor with the code **`000000`**.

| Role       | Email                              |
|------------|------------------------------------|
| Student    | `buckeye.1@osu.edu`                |
| Student    | `scarlet.2@osu.edu`                |
| Professor  | `weide.1@osu.edu`                  |
| Professor  | `gomez.2@osu.edu`                  |
| Admin      | `admin@osu.edu`                    |
| Recruiter  | `recruiter.google@learnpp.test`    |
| Recruiter  | `recruiter.amazon@learnpp.test`    |

---

## Features → PRD mapping

| Feature | Where |
|---|---|
| Course forums, access limited to enrolled members | `web/routes.py` (forums) + `web/access.py` |
| Auto-decomposed interactive lessons for assignments due ≤ 7 days | `services/lesson_service.py`, `services/decompose_service.py` |
| Gamified staged flow (XP, progress, daily goal, streak) | `services/flow_service.py`, `frontend/js/views.js` (lessonFlow) |
| Interactive "Coach" tutor (multi-turn, anti-copy-paste) | `services/tutor_service.py`, `frontend/js/views.js` |
| Compile + review/consent gate (content-hash) | `services/compile_service.py`, `frontend/js/views.js` (compile) |
| Study planner + reflow (backward from due date, daily cap, backlog) | `services/planner_service.py` |
| Learning-style preferences (max 2 + notes) | `services/preferences_service.py` |
| **Portfolio**: AI skills from completed work → recommended projects → "Get Help" lessons → resume view | `services/portfolio_service.py`, `frontend/js/views.js` (portfolio) |
| AI over urllib (decompose JSON + Coach chat) with offline mocks | `integrations/gemini_service.py`, `services/ai_mock.py` |
| Projects: guided (course-scoped) + showcase (recruiter-visible) + comments | `web/routes.py` (projects) |
| Announcements (events / study / exams / resources) | `web/routes.py` (announcements) |
| Schedule advisor via OSU class search | `integrations/osu_classsearch.py` |
| Profiles with GitHub/LinkedIn, **no social media**, avatars | `web/routes.py` (users) |
| 4-role login + OSU verification + 2FA | `web/routes.py` (auth), `integrations/osu_auth.py` |
| Canvas scrape (courses, calendar, members/roles) via Playwright | `integrations/canvas_scraper.py`, `services/onboarding_service.py` |
| User database (MySQL in prod) | `db/database.py` + `docs/MIGRATION.md` |
| Collapsible sidebar + mobile bottom bar | `frontend/` |
| Recruiters restricted to showcase, only if on registry | `web/routes.py`, `web/access.py`, admin registry |

---

## Verifying it works

Run the end-to-end smoke test (server must be running):

```bash
python -m backend.app.main &        # start server
python backend/scripts/smoke_test.py
```

It exercises the full app — role login, course-scoped access, recruiter
restrictions, the interactive lesson engine (decompose, gamified flow with XP,
Coach tutor, challenge/draft, compile + consent gate, learning preferences,
planner/backlog), the Portfolio (skills, project guide, "Get Help"), forums,
moderation, projects, profiles, admin registry — and prints a pass/fail summary
(59 checks).

---

## Deployment target (Ubuntu VM on Mac)

The PRD specifies the backend runs on an **Ubuntu VM** with the UI on
**localhost**, using **MySQL** and the **real** Canvas / OSU / Gemini
integrations. This repo is built to run **identically** offline (SQLite + mock
integrations) and in production (MySQL + live integrations):

- **Enable real Gemini**: set `GEMINI_API_KEY` (and optionally `GEMINI_MODEL` /
  `GEMINI_FALLBACKS`) in `backend/.env` or the environment. The lesson engine
  then calls the real Gemini REST API over `urllib` (no pip installs) for
  decompose + the Coach tutor + feedback, with automatic model fallback on
  overload and a graceful drop back to the offline mock. See `.env.example`.
- **Enable MySQL**: see [`docs/MIGRATION.md`](docs/MIGRATION.md).
- **Enable real Canvas/OSU**: `pip install playwright && playwright install
  chromium`, then flip `USE_MOCK_INTEGRATIONS=0`. Integration points are stubbed
  with clear `NotImplementedError`s in `integrations/`.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design and
[`docs/RUNBOOK.md`](docs/RUNBOOK.md) for VM setup steps.

---

## Project layout

```
backend/
  app/
    core/          config + security (JWT, password hashing)
    db/            SQLite data-access layer + repository (swappable to MySQL)
    integrations/  Gemini (urllib JSON + chat), Canvas (Playwright), OSU auth/search
    services/      lesson engine: decompose, resolve, tutor, flow, compile,
                   planner, preferences, portfolio, lesson_service (Canvas
                   autogen), ai_mock (offline AI), onboarding
    web/           tiny HTTP router, access control, routes
    main.py        server entrypoint (API + static UI, one origin)
  scripts/         seed.py, smoke_test.py
frontend/          single-page UI (vanilla JS, no build step):
                   index.html shell, css/styles.css, js/{api,views,app}.js
docs/              architecture, migration, runbook
```
