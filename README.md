# learning++ &nbsp;·&nbsp; `lesson-engine`

Turn your Canvas assignments into short daily **mini-lessons** that actually teach
you — then compile your own work into a submission. Built for students who are
busy and tired of grinding homework alone.

This repo is the **backend engine** (a Node + Fastify API). The user-facing
website is a **separate** static HTML/CSS/JS app that calls this API. If you're
building the frontend, start with **[`docs/INTEGRATION.md`](docs/INTEGRATION.md)** —
it lists every endpoint and its JSON shapes.

---

## What it does (the 60-second version)

1. **Ingest** an assignment (paste its text; Canvas auto-ingest is a later step).
2. **Decompose** it with AI into a sequence of ~10–15 min lessons.
3. **Find resources** — a relevant YouTube video + a reading excerpt (from an
   uploaded textbook PDF, else Wikipedia).
4. **Learn it** as a gamified **staged flow**: intro → watch → read → bite-size
   challenges → draft the real deliverable, with **"Coach"** (an AI tutor) giving
   live feedback and **never writing your answer for you**. XP, streak, progress.
5. **Plan** lessons across days, backward from the due date, so you never cram.
6. **Compile** your own answers into a submission bundle — behind a required
   **review + consent** step, with a clear list of what's still left.

The guiding principle: **make you genuinely learn, not copy-paste an AI answer.**

---

## Quick start

> Prereqs: **Node.js 20+** (22 recommended) and **npm**. A free **Gemini API key**
> ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)). Optional: a
> free **YouTube Data API v3 key** (Google Cloud Console).

```bash
git clone https://github.com/prudhviadari-osu/lesson-engine.git
cd lesson-engine
npm install                 # compiles better-sqlite3 (needs build tools — see below)
cp .env.example .env        # then edit .env and paste your GEMINI_API_KEY
npm run seed                # create learning.db with a demo assignment
npm start                   # → http://localhost:3000
```

Open **http://localhost:3000** for the built-in **test harness** — a plain page
that lets you click through the whole pipeline (profile → paste assignment →
decompose → find videos/reading → play the gamified lesson → compile). The
harness is a debugging tool, **not** the real UI — that's the frontend repo.

**On Linux**, `better-sqlite3` compiles native code, so you need build tools first:
```bash
sudo apt install -y build-essential python3
```

---

## Configuration (`.env`)

Copy `.env.example` → `.env` and fill it in. The only **required** value is
`GEMINI_API_KEY`. Everything else has sane defaults. See `.env.example` for the
full annotated list (model fallbacks, YouTube key, XP/goal dials, planner knobs).

**Never commit your real `.env`** — it's gitignored for a reason (it holds keys).

### Gotchas we hit (so you don't have to)
- **"model is no longer supported"** → Google rotated models. Change
  `GEMINI_MODEL` in `.env` to a current one (e.g. `gemini-3.8-flash`) and restart.
- **"high demand / overloaded"** → the free tier under load. The server auto-
  retries and falls back to lighter models; usually just retry. Successful AI
  results are **cached**, so re-running the same decompose is instant and offline.
- **`no such column` SQL error after `git pull`** → the DB schema changed. Run
  `npm run seed` to rebuild `learning.db`. (SQLite can't auto-add columns.)
  Re-seeding wipes local data — it's only demo data.

---

## Project layout

```
src/
  server.js            Fastify app: CORS, static harness, route registration
  db/
    schema.sql         full SQLite schema (source of truth)
    index.js           DB connection + initSchema()
    seed.js            demo fixture (1 user, 1 assignment, 2 lessons)
  routes/index.js      ALL HTTP routes
  services/
    gemini.js          Gemini client: generateJSON + generateText, retry/fallback, cache
    decompose.js       assignment → lessons (honors learning-style prefs)
    youtube.js         YouTube video search (keyless fallback = search link)
    reading.js         textbook-PDF excerpt match, else Wikipedia
    resolve.js         fill video/reading blocks for an assignment
    users.js           lightweight profiles + learning preferences
    planner.js         schedule lessons backward from due date + reflow
    tutor.js           "Coach" chat tutor (persona + sessions)
    flow.js            the gamified STAGED LESSON FLOW + XP
    compile.js         assemble submission + review/consent gate
public/index.html      the test harness (debug UI)
docs/
  INTEGRATION.md       API contract for the frontend team  ← read this to build the UI
SPEC.md                the original product spec
```

---

## Scripts

| Command | What it does |
|---|---|
| `npm start` | Run the API on `http://localhost:3000` |
| `npm run dev` | Same, auto-restart on file changes |
| `npm run seed` | (Re)build `learning.db` with the demo fixture |

---

## How it fits together (30-second mental model)

- **`server.js`** wires up Fastify (CORS on), serves the test harness, and
  registers all routes.
- **`routes/index.js`** is the one place every HTTP endpoint lives. Each route is
  thin: it figures out the user (`resolveUserId`) and calls a **service**.
- **`services/`** is where the real logic is, one file per concern (see the
  layout above). `gemini.js` is the shared AI client (used by decompose, tutor,
  flow) with retry/fallback/caching built in.
- **`db/`** — one SQLite file (`learning.db`); `schema.sql` is the source of
  truth; everything is scoped to a user via `course.user_id`.
- Data flow for a lesson: **paste → decompose (AI) → resources (YouTube/Wiki) →
  staged flow (learn + answer) → compile (assemble your answers) → consent**.

## For the team

- **Frontend devs:** everything you need is in
  [`docs/INTEGRATION.md`](docs/INTEGRATION.md) — endpoints, request/response
  shapes, the `x-user-id` convention, CORS. You never need to read backend code.
- **Product context:** [`SPEC.md`](SPEC.md).
- **Backend:** each route in `src/routes/index.js` maps to a `src/services/*`
  file — start there to add or change a feature.

## Status

Done: profiles + learning prefs · paste ingest · AI decompose · resource-find
(YouTube + Wikipedia/PDF) · gamified staged lesson flow + "Coach" tutor ·
planner + reflow · compile with review/consent gate.
Next / experimental: Canvas auto-ingest (Playwright), multi-LMS, voice mode.
