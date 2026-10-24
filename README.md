# learning++ (backend)

Standalone Fastify + SQLite API that turns Canvas assignments into daily mini-lessons.
The frontend is a **separate** static HTML/CSS/JS app (teammate's repo) that calls this API.

## Run (inside the Ubuntu VM)

```bash
npm install
cp .env.example .env     # then edit .env and paste your GEMINI_API_KEY
npm run seed             # creates learning.db with one demo assignment
npm start                # http://localhost:3000  (test harness at /)
```

Get a free Gemini key at <https://aistudio.google.com/apikey>.

Open <http://localhost:3000> for the throwaway test harness: load today's plan,
do a lesson (watch video / read excerpt / answer / flashcards), complete it,
then compile the "submission".

## Build status

- [x] **Step 1 — Spine:** Fastify + SQLite + CORS, schema, seed, test harness,
      routes: `/health /courses /assignments/:id /lessons/:id /blocks/:id/answer
      /lessons/:id/complete /assignments/:id/compile /plan`
- [x] **Step 2 — Gemini decompose:** `POST /ingest/paste` + `POST /assignments/:id/decompose`.
      Paste a real assignment -> Gemini returns structured lessons (video/excerpt/
      scaffold_q/draft/flashcards). Responses cached in `resource_cache` (demo-safety).
      Resource blocks (video/excerpt) carry a search query/topic, resolved in Step 3.
- [x] **Step 3 — Resource-find:** `POST /assignments/:id/resources` resolves
      video blocks via YouTube Data API (keyless fallback = search link) and
      excerpt blocks via uploaded textbook PDF (`POST /assignments/:id/textbook`)
      else Wikipedia. All results cached. YouTube needs `YOUTUBE_API_KEY`.
- [x] **Users + learning prefs:** lightweight profiles (no passwords). `user`
      table holds `display_name`, `learning_styles` (1-2 of visual/auditory/
      reading/kinesthetic), `learning_notes` (free text). All data scoped to a
      user; identity via `x-user-id` header or `?userId=`. Prefs are injected
      into the Gemini decompose prompt to tailor the lesson mix.
      Routes: `GET/POST/PATCH/DELETE /users[/:id]`.
      Assignment CRUD: `GET /assignments`, `PATCH/DELETE /assignments/:id`.
      **NOTE: schema changed — run `npm run seed` to rebuild `learning.db`.**
- [x] **Step 4 — Planner + reflow:** deterministic scheduler (backward from due
      date, submission buffer, daily cap, over-capacity flagged not crammed).
      `POST /plan/reflow` (generate/reflow), `GET /plan` (scheduled days +
      unscheduled backlog), `DELETE /plan/lessons/:id` (unschedule -> backlog),
      `POST /plan/lessons/:id/reschedule`, `DELETE /plan` (clear all -> backlog).
      Plan edits touch ONLY plan_entry — never lessons/answers — so compile
      still reports unwritten work as "not done" regardless of the schedule.
- [ ] Step 5 — Compile + review/consent
- [x] **Interactive Tutor ("Coach"):** live multi-turn tutor (`generateText()`,
      warm temp 0.9) that teaches in bites and reacts to the student's answers,
      never writing them. `tutor_message` table. `GET/POST/DELETE /lessons/:id/tutor`.
- [x] **Unified gamified STAGED LESSON FLOW (the main experience):** a lesson is
      an ordered journey (intro → watch video → read excerpt → bite-size
      challenges w/ instant feedback → draft the deliverable w/ Coach feedback →
      complete), derived from existing blocks. Resolved video + reading surfaced
      IN-flow. Gamification: XP per stage (5/10/10/15/25 + 20 bonus), lesson
      progress %, daily XP goal (50), streak. New `user_xp` + `xp_event` tables
      (RE-SEED needed). Routes: `GET /lessons/:id/flow`, `POST .../flow/advance`,
      `.../flow/challenge`, `.../flow/draft`, `.../flow/complete`. Answers save to
      the answer table BEFORE any Gemini call, so work/XP never lost on no-key or
      overload — and compile stays answer-driven (verified).
- [ ] Step 6 — Playwright ingestion

See `../SPEC.md` for the full plan.

## Notes
- CORS is wide-open (`origin: true`) for the hackathon so the teammate's static
  page can call it from any origin. Tighten before real use.
- DB file: `learning.db` (set `DB_PATH` to override). `npm run seed` resets it.
