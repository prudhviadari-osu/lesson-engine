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
- [ ] Step 3 — Resource-find (YouTube + PDF excerpt)
- [ ] Step 4 — Planner + reflow
- [ ] Step 5 — Compile + review/consent
- [ ] Step 6 — Playwright ingestion

See `../SPEC.md` for the full plan.

## Notes
- CORS is wide-open (`origin: true`) for the hackathon so the teammate's static
  page can call it from any origin. Tighten before real use.
- DB file: `learning.db` (set `DB_PATH` to override). `npm run seed` resets it.
