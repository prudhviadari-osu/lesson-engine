# learning++ &nbsp;·&nbsp; HACK OH/IO

> **Climb the material — don't just finish the assignment.**

learning++ turns a student's coursework into an **interactive, gamified mastery
climb**: the real homework questions are the spine, wrapped in short AI-tutored
steps that teach each skill and check it, so you actually *learn* the material
instead of copy-pasting an AI answer. It's built around a mountain-climbing
metaphor — each day is a paced ascent toward a summit, no cramming.

Around the lesson engine sits a full campus platform — course forums, a project
showcase for recruiters, announcements, a schedule advisor, customizable
profiles, a study planner, and an AI-built **Portfolio** — all under role-based
access for Students, Professors, Administration, and Verified Recruiters.

**One unified Python app, standard-library only** (a hand-rolled HTTP router,
SQLite, stdlib JWT — no `pip install` needed) serving a vanilla-JS single-page
UI on one origin. It runs fully offline.

---

## The lesson experience (the heart of it)

A lesson is a **staged mastery climb**, and the climb *is* the real assignment:

1. **The real homework is the spine.** Each assignment's actual questions become
   "draft" work stages — you do your genuine coursework inside the tool.
2. **AI mastery supplements wrap around them** — a short teaching clip/reading, a
   mix of **multiple-choice** and **short-answer** checks (instant green/coral
   feedback), building you up to nail *those specific* questions.
3. **Coach** — a live AI tutor that teaches in small bites, reacts to what you
   actually type, and **never writes your answer for you**.
4. **Gamified & paced** — XP per stage, a progress ring, a daily XP goal, a
   streak, and a celebratory summit when you finish. The planner spreads lessons
   backward from each due date within the time you have (an adjustable **1–6 h /
   day** budget), so work is front-loaded, never crammed.
5. **Compile + consent** — assembles *your own* answers into a submission bundle,
   grouped by lesson, and only marks it "ready" after you review + consent
   (editing an answer invalidates prior consent — honesty by design).
6. **Portfolio** — from work you *actually completed*, AI extracts resume-worthy
   skills and recommends projects; "Get Help" turns a recommendation into a real
   playable lesson. Nothing is credited that you didn't finish.

---

## Quick start

No third-party packages required — Python standard library + SQLite out of the box.

> **Run from the repository root** — the folder that *contains* `backend/` (not
> from inside `backend/`), or you'll get `No module named backend`. `ls` should
> show `backend/` first. Use `python3` if `python` isn't Python 3.

```bash
# 1. Seed the demo data
python3 -m backend.scripts.seed

# 2. Start the server (serves the API + UI on one origin)
python3 -m backend.app.main

# 3. Open the UI
#    http://127.0.0.1:8000
```

> Requires Python 3.10+ (tested on 3.11–3.13).

### Try the demo

Log in as the demo student and open the ECE 2060 climb:

| Field | Value |
|---|---|
| Email | `buckeye.1@osu.edu` |
| Password | `Password123` |
| OSU 2FA code | `000000` |

Other seeded logins: professors `weide.1@osu.edu` / `gomez.2@osu.edu`, admin
`admin@osu.edu`, recruiters `recruiter.google@learnpp.test` /
`recruiter.amazon@learnpp.test` (same password; students/professors use 2FA
`000000`).

---

## AI keys & mock mode (no setup needed to run)

The app runs out of the box with **no API key and no `.env`**:

- **`buckeye.1` is the demo account** — always runs on built-in demo content
  (the deep ECE 2060 "Number Systems" climb), so the demo is fully reliable with
  no key and no network.
- **Any other account** uses **live AI** with a key you paste on the in-app
  **Account Settings** page. The key is held **in memory for that session only**
  — never written to `.env`, disk, or the database, and cleared on logout. Get a
  free Gemini key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
- **Canvas ingestion is pending** — we're applying for Canvas **OAuth2** approved-
  integration access. Until then, non-demo accounts honestly show a *"Canvas
  integration coming soon"* empty state rather than fake data.

(A server-wide `GEMINI_API_KEY` / `YOUTUBE_API_KEY` can optionally be set in
`backend/.env` as a dev fallback — see `backend/.env.example` — but it's not
required.)

---

## Verifying it works

```bash
python3 -m backend.app.main &            # start the server
python3 backend/scripts/smoke_test.py    # 59 checks
```

Exercises the whole app end-to-end: role login + OSU 2FA, course-scoped access,
recruiter restrictions, the lesson engine (decompose → gamified staged flow with
XP/MCQ/short-answer → Coach tutor → compile + consent gate → learning
preferences → planner/backlog), the Portfolio, forums, moderation, projects,
profiles, and the admin registry. Prints a pass/fail summary.

---

## Tech & architecture

- **Backend:** Python standard library only — `http.server` + a ~100-line
  path-pattern router, `sqlite3`, and a hand-written HS256 JWT. Zero runtime
  `pip` dependencies.
- **AI:** Gemini via `urllib` — structured JSON for decompose, warm free-text for
  the Coach tutor + feedback, with automatic model fallback on overload. Keyless
  → deterministic offline mocks so everything still works.
- **Resources:** YouTube Data API for in-flow videos, Wikipedia for readings
  (both degrade to a search link without a key).
- **Frontend:** vanilla HTML/CSS/JS single-page app, no build step.
- **Data:** SQLite locally; the data-access layer isolates all SQL so it can be
  swapped to MySQL in production (see [`docs/MIGRATION.md`](docs/MIGRATION.md)).

### Roadmap
- Canvas **OAuth2** integration (approval pending) to auto-import real coursework.
- A local **Ollama** model as an offline AI fallback (no key needed).
- Web-crawled supplementary resources.

---

## Project layout

```
backend/
  app/
    core/          config, security (JWT, password hashing), per-session API keys
    db/            SQLite data-access layer + repository (swappable to MySQL)
    integrations/  Gemini (urllib), Canvas/OSU stubs (OAuth2 pending)
    services/      lesson engine: decompose, resolve, tutor, flow, compile,
                   planner, preferences, portfolio, lesson/onboarding, ai_mock
    web/           tiny HTTP router, access control, routes
    main.py        server entrypoint (API + static UI on one origin)
  scripts/         seed.py, smoke_test.py
frontend/          single-page UI (vanilla JS): index.html, css/, js/
docs/              architecture, migration, runbook
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.
