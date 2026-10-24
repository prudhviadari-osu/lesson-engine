# learning++ (backend)

Standalone Fastify + SQLite API that turns Canvas assignments into daily mini-lessons.
The frontend is a **separate** static HTML/CSS/JS app (teammate's repo) that calls this API.

## Run (inside the Ubuntu VM)

```bash
npm install
npm run seed     # creates learning.db with one demo assignment
npm start        # http://localhost:3000  (test harness at /)
```

Open <http://localhost:3000> for the throwaway test harness: load today's plan,
do a lesson (watch video / read excerpt / answer / flashcards), complete it,
then compile the "submission".

## Build status

- [x] **Step 1 — Spine:** Fastify + SQLite + CORS, schema, seed, test harness,
      routes: `/health /courses /assignments/:id /lessons/:id /blocks/:id/answer
      /lessons/:id/complete /assignments/:id/compile /plan`
- [ ] Step 2 — Gemini decompose
- [ ] Step 3 — Resource-find (YouTube + PDF excerpt)
- [ ] Step 4 — Planner + reflow
- [ ] Step 5 — Compile + review/consent
- [ ] Step 6 — Playwright ingestion

See `../SPEC.md` for the full plan.

## Notes
- CORS is wide-open (`origin: true`) for the hackathon so the teammate's static
  page can call it from any origin. Tighten before real use.
- DB file: `learning.db` (set `DB_PATH` to override). `npm run seed` resets it.
