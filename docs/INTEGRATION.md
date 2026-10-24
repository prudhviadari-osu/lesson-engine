# Integration Guide — learning++ API

This is everything the **frontend** needs to talk to the backend. You do not need
to read the backend source. If something here is wrong or missing, ping the
backend owner — don't guess.

- **Base URL (local dev):** `http://localhost:3000`
- **CORS:** open (`origin: true`) — your static page can call it from any origin.
- **Content type:** send JSON bodies with `Content-Type: application/json`.
  File uploads use `multipart/form-data`.
- **Responses:** always JSON. Errors look like `{ "error": "message" }` with an
  HTTP status (400 bad input, 404 not found, 409 conflict, 503 AI overloaded).

## "Who am I" — the user header

Everything is scoped to a **user profile** (lightweight, no passwords). Send the
acting user's id on every request as a header:

```
x-user-id: 1
```

(You can also use `?userId=1`.) If omitted, the server falls back to the first
user. Typical flow: on load, `GET /users`; let the person pick/create a profile;
then send its id as `x-user-id` on all subsequent calls.

---

## Endpoints by feature

### Profiles & learning preferences
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/users` | — | `{ users: [{ id, displayName, learningStyles[], learningNotes }] }` |
| GET | `/users/:id` | — | `{ id, displayName, learningStyles[], learningNotes }` |
| POST | `/users` | `{ displayName, learningStyles?[], learningNotes? }` | the created user (201) |
| PATCH | `/users/:id` | any of `{ displayName, learningStyles[], learningNotes }` | the updated user |
| DELETE | `/users/:id` | — | `{ ok }` |

`learningStyles` = **0–2** of `"visual" | "auditory" | "reading" | "kinesthetic"`
(3+ → 400). These + `learningNotes` (free text) tailor the AI lessons.

### Assignments
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/ingest/paste` | `{ title, text, dueAt?, points?, courseName? }` | `{ ok, assignmentId, courseId }` |
| GET | `/assignments` | — | `{ assignments: [ ... ] }` (this user's, flat) |
| GET | `/assignments/:id` | — | the assignment + its `lessons[]` |
| PATCH | `/assignments/:id` | any of `{ title, text, dueAt, points, submissionType }` | `{ ok, assignment }` |
| DELETE | `/assignments/:id` | — | `{ ok, deleted }` (cascades lessons/answers) |
| POST | `/assignments/:id/decompose` | — | `{ lessonCount, lessons[], appliedProfile }` — AI splits it into lessons |
| POST | `/assignments/:id/resources` | — | `{ resolvedVideos, resolvedReadings, totalResourceBlocks }` — fills video/reading |
| POST | `/assignments/:id/textbook` | multipart, field `file` (PDF) | `{ ok, attachmentId, filename, bytes }` |

`dueAt` is ISO-8601 (e.g. `"2026-05-01T23:59:00"`). Decompose/resources/tutor
need `GEMINI_API_KEY` set on the server; if it's missing they return **400**
`{ error, code: "NO_API_KEY" }`. If the AI is overloaded, **503**
`{ error, retryable: true }` — just retry.

### Lessons (raw)
| Method | Path | Returns |
|---|---|---|
| GET | `/lessons/:id` | `{ ...lesson, blocks: [{ id, seq, type, payload }] }` |
| POST | `/lessons/:id/complete` | `{ ok }` — marks done + bumps streak |
| POST | `/blocks/:id/answer` | body `{ content }` → `{ ok, answerId }` — save an answer |

Block `type` ∈ `video | excerpt | scaffold_q | draft | flashcards`. **Most UIs
should use the staged flow below instead of raw blocks.**

### Staged lesson flow  ← the main "do a lesson" experience
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/lessons/:id/flow` | — | the full staged journey + progress + gamification (below) |
| POST | `/lessons/:id/flow/advance` | `{ stageKey }` | marks an intro/video/reading stage done, awards XP |
| POST | `/lessons/:id/flow/challenge` | `{ stageKey, answer }` | `{ correct, feedback, revealed?, xpAwarded, gamification }` |
| POST | `/lessons/:id/flow/draft` | `{ stageKey, content }` | `{ feedback, xpAwarded, gamification }` (Coach never rewrites) |
| POST | `/lessons/:id/flow/complete` | — | `{ lessonComplete, completionBonus, gamification }` |

**`GET /lessons/:id/flow` shape:**
```jsonc
{
  "lessonId": 1, "lessonTitle": "...", "lessonStatus": "todo",
  "assignment": { "id": 1, "title": "..." },
  "stages": [
    { "key": "intro",      "type": "intro",   "title": "...", "xp": 5,  "done": false, "body": "..." },
    { "key": "video:2",    "type": "video",   "title": "Watch", "xp": 10, "done": false,
      "payload": { "title","channel","url","embedUrl","thumbnail","resolved" } },
    { "key": "reading:3",  "type": "reading", "title": "Read",  "xp": 10, "done": false,
      "payload": { "source","heading","text","url","resolved" } },
    { "key": "challenge:4","type": "challenge","title":"Challenge","xp":15,"done":false,
      "challengeKind": "scaffold|flashcard", "prompt": "...", "hint": "...", "savedAnswer": "..." },
    { "key": "draft:6",    "type": "draft",   "title":"Draft the deliverable","xp":25,"done":false,
      "prompt": "...", "rubricHint": "...", "savedAnswer": "..." },
    { "key": "complete",   "type": "complete","title":"Complete!","xp":20,"done":false }
  ],
  "progress": { "stagesTotal": 6, "stagesDone": 2, "progressPct": 33, "lessonComplete": false },
  "gamification": { "totalXp": 35, "dailyGoal": 50, "dailyXp": 35, "dailyGoalPct": 70,
                    "dailyGoalMet": false, "todayStreak": 1 }
}
```
UI guide: render stages in order as a path. For `video`/`reading`, embed
`payload.embedUrl` / show `payload.text` then call `advance`. For `challenge`/
`draft`, show `prompt`, take the user's input, POST it, show `feedback` (and
`correct` ✓/try-again). XP/progress to drive bars come back on every call.

### Interactive tutor ("Coach") — optional free-form chat
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/lessons/:id/tutor` | — | `{ history: [{ role, content }] }` |
| POST | `/lessons/:id/tutor/start` | `{ reset? }` | `{ history, ... }` (Coach opens) |
| POST | `/lessons/:id/tutor` | `{ message }` | `{ reply, history }` |
| DELETE | `/lessons/:id/tutor` | — | `{ ok, cleared }` |

`role` is `"user"` (student) or `"model"` (Coach).

### Planner
| Method | Path | Returns |
|---|---|---|
| GET | `/plan` | scheduled `days[]` + `unscheduled[]` backlog + `todayStreak`, `dailyCapMin` |
| POST | `/plan/reflow` | regenerate the schedule (backward from due dates) |
| DELETE | `/plan/lessons/:lessonId` | unschedule → moves to backlog |
| POST | `/plan/lessons/:lessonId/reschedule` | pull a backlog lesson back in |
| DELETE | `/plan` | clear whole schedule → everything to backlog |

A `day` = `{ date, loadMinutes, overCapacity, lessons: [{ lessonId, title, estMinutes, assignment }] }`.
Unscheduling/clearing only moves things on the calendar — it never deletes
answers, and never changes what compile reports.

### Compile + submit (review & consent)
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/assignments/:id/compile` | — | the compiled submission (below) |
| POST | `/assignments/:id/compile/consent` | `{ reviewed: true, consented: true, contentHash }` | updated compile |

**`GET /assignments/:id/compile` shape:**
```jsonc
{
  "assignmentId": 1, "title": "...", "dueAt": "...",
  "complete": false,
  "totals": { "totalItems": 3, "doneItems": 1, "deliverables": 1, "deliverablesDone": 0 },
  "byLesson": [ { "lessonId", "title", "items": [ { "kind":"deliverable|reflection","label","answer","done" } ] } ],
  "missing": [ "label", ... ],
  "missingByLesson": [ { "lessonId","title","lessonStarted","missing":[{ "kind","label" }] } ],
  "compiledText": "# ...markdown submission...",
  "contentHash": "abc123...",
  "review": { "readyToSubmit": false, "reviewed": false, "consented": false, "consentStale": false }
}
```
**Flow for the UI:** show `compiledText` + the `missingByLesson` checklist. To
mark it ready, make the user tick "I reviewed this" and "I consent", then POST
to `/compile/consent` with **the `contentHash` from the GET**. If they later edit
an answer, `review.consentStale` becomes `true` and `readyToSubmit` flips back to
`false` — re-fetch compile and have them review again. Posting a stale hash → 409.

---

## Minimal example (vanilla JS)

```js
const API = 'http://localhost:3000';
const userId = 1;
const call = (path, opts = {}) => fetch(API + path, {
  ...opts,
  headers: { 'Content-Type': 'application/json', 'x-user-id': String(userId), ...(opts.headers || {}) },
}).then(r => r.json());

// paste → decompose → find resources → open the staged flow
const { assignmentId } = await call('/ingest/paste', {
  method: 'POST', body: JSON.stringify({ title: 'Essay', text: 'Write 500 words on ...' }),
});
await call(`/assignments/${assignmentId}/decompose`, { method: 'POST' });
await call(`/assignments/${assignmentId}/resources`, { method: 'POST' });
const asg = await call(`/assignments/${assignmentId}`);
const flow = await call(`/lessons/${asg.lessons[0].id}/flow`);
```
