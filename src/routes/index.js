import { db } from '../db/index.js';
import { decomposeAssignment } from '../services/decompose.js';
import { resolveResources } from '../services/resolve.js';
import {
  listUsers, getUser, createUser, updateUser, deleteUser, resolveUserId,
} from '../services/users.js';
import {
  generatePlan, getPlan, unscheduleLesson, rescheduleLesson, clearPlan,
} from '../services/planner.js';
import { writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const UPLOAD_DIR = join(__dirname, '..', '..', 'uploads');

// Spine routes (SPEC §8). More arrive in later build steps:
// resources, planner/reflow, compile/consent, ingestion.
export async function registerRoutes(app) {
  // Health
  app.get('/health', async () => ({ ok: true, service: 'learning++', step: 'planner' }));

  // --- Users / profiles (lightweight; no passwords) --------------------------
  app.get('/users', async () => ({ users: listUsers() }));

  app.get('/users/:id', async (req, reply) => {
    const u = getUser(req.params.id);
    if (!u) return reply.code(404).send({ error: 'user not found' });
    return u;
  });

  app.post('/users', async (req, reply) => {
    try {
      const { displayName, learningStyles, learningNotes } = req.body ?? {};
      return reply.code(201).send(createUser({ displayName, learningStyles, learningNotes }));
    } catch (err) {
      if (err.code === 'BAD_INPUT') return reply.code(400).send({ error: err.message });
      throw err;
    }
  });

  app.patch('/users/:id', async (req, reply) => {
    try {
      const { displayName, learningStyles, learningNotes } = req.body ?? {};
      return updateUser(req.params.id, { displayName, learningStyles, learningNotes });
    } catch (err) {
      if (err.code === 'NOT_FOUND') return reply.code(404).send({ error: 'user not found' });
      if (err.code === 'BAD_INPUT') return reply.code(400).send({ error: err.message });
      throw err;
    }
  });

  app.delete('/users/:id', async (req, reply) => {
    return { ok: deleteUser(req.params.id) };
  });

  // --- Ingest: manual paste (always-works fallback, SPEC §4) -----------------
  // Creates a course (if needed) + assignment from pasted text. No Canvas needed.
  app.post('/ingest/paste', async (req, reply) => {
    const userId = resolveUserId(req);
    if (!userId) return reply.code(400).send({ error: 'no user — create a profile first (POST /users)' });
    const { title, text, courseName, dueAt, points, submissionType } = req.body ?? {};
    if (!title || !text) {
      return reply.code(400).send({ error: 'title and text are required' });
    }
    // Reuse this user's "Pasted assignments" course, or make one.
    const cname = courseName || 'Pasted assignments';
    let course = db.prepare('SELECT * FROM course WHERE name = ? AND user_id = ?').get(cname, userId);
    if (!course) {
      const r = db.prepare('INSERT INTO course (user_id, name) VALUES (?, ?)').run(userId, cname);
      course = { id: r.lastInsertRowid };
    }
    const res = db.prepare(
      `INSERT INTO assignment (course_id, title, description_text, due_at, points, submission_type, source, status)
       VALUES (?, ?, ?, ?, ?, ?, 'paste', 'ingested')`
    ).run(course.id, title, text, dueAt || null, points ?? null, submissionType || 'online_text_entry');
    return { ok: true, assignmentId: res.lastInsertRowid, courseId: course.id };
  });

  // --- Decompose: assignment -> lessons via Gemini (SPEC §11 step 2) ---------
  app.post('/assignments/:id/decompose', async (req, reply) => {
    try {
      const userId = resolveUserId(req);
      const user = userId ? getUser(userId) : null;
      const result = await decomposeAssignment(req.params.id, user);
      return { ...result, appliedProfile: user ? { learningStyles: user.learningStyles, learningNotes: user.learningNotes } : null };
    } catch (err) {
      if (err.code === 'NOT_FOUND') return reply.code(404).send({ error: 'assignment not found' });
      if (err.code === 'NO_API_KEY') return reply.code(400).send({ error: err.message });
      if (err.code === 'OVERLOADED') return reply.code(503).send({ error: err.message, retryable: true });
      app.log.error(err);
      return reply.code(502).send({ error: 'decompose failed', detail: err.message, raw: err.raw });
    }
  });

  // --- Resolve resources: fill video/excerpt blocks (SPEC §11 step 3) --------
  app.post('/assignments/:id/resources', async (req, reply) => {
    try {
      return await resolveResources(req.params.id);
    } catch (err) {
      if (err.code === 'NOT_FOUND') return reply.code(404).send({ error: 'assignment not found' });
      app.log.error(err);
      return reply.code(502).send({ error: 'resource resolution failed', detail: err.message });
    }
  });

  // --- Textbook PDF upload (multipart) ---------------------------------------
  app.post('/assignments/:id/textbook', async (req, reply) => {
    const asg = db.prepare('SELECT id FROM assignment WHERE id = ?').get(req.params.id);
    if (!asg) return reply.code(404).send({ error: 'assignment not found' });

    const file = await req.file();
    if (!file) return reply.code(400).send({ error: 'no file uploaded (field name "file")' });

    mkdirSync(UPLOAD_DIR, { recursive: true });
    const safeName = `${Date.now()}-${file.filename.replace(/[^\w.\-]/g, '_')}`;
    const localPath = join(UPLOAD_DIR, safeName);
    const buf = await file.toBuffer();
    writeFileSync(localPath, buf);

    const res = db.prepare(
      `INSERT INTO attachment (assignment_id, filename, local_path, mime, kind)
       VALUES (?, ?, ?, ?, 'uploaded_textbook')`
    ).run(asg.id, file.filename, localPath, file.mimetype || 'application/pdf');

    return { ok: true, attachmentId: res.lastInsertRowid, filename: file.filename, bytes: buf.length };
  });

  // --- Courses + assignments (scoped to the acting user) ---------------------
  app.get('/courses', async (req) => {
    const userId = resolveUserId(req);
    const courses = db.prepare('SELECT * FROM course WHERE user_id = ? ORDER BY id').all(userId);
    const asgStmt = db.prepare('SELECT * FROM assignment WHERE course_id = ? ORDER BY id');
    return courses.map((c) => ({ ...c, assignments: asgStmt.all(c.id) }));
  });

  // Flat list of the user's assignments (so the tool can show add/remove list)
  app.get('/assignments', async (req) => {
    const userId = resolveUserId(req);
    const rows = db.prepare(
      `SELECT a.* FROM assignment a JOIN course c ON c.id = a.course_id
        WHERE c.user_id = ? ORDER BY a.due_at, a.id`
    ).all(userId);
    return { assignments: rows };
  });

  app.get('/assignments/:id', async (req, reply) => {
    const asg = db.prepare('SELECT * FROM assignment WHERE id = ?').get(req.params.id);
    if (!asg) return reply.code(404).send({ error: 'assignment not found' });
    const lessons = db.prepare('SELECT * FROM lesson WHERE assignment_id = ? ORDER BY seq').all(asg.id);
    return { ...asg, lessons };
  });

  // Edit an assignment's fields (title/text/due/points). Does NOT re-decompose.
  app.patch('/assignments/:id', async (req, reply) => {
    const asg = db.prepare('SELECT * FROM assignment WHERE id = ?').get(req.params.id);
    if (!asg) return reply.code(404).send({ error: 'assignment not found' });
    const { title, text, dueAt, points, submissionType } = req.body ?? {};
    db.prepare(
      `UPDATE assignment SET title = ?, description_text = ?, due_at = ?, points = ?, submission_type = ?
        WHERE id = ?`
    ).run(
      title ?? asg.title,
      text ?? asg.description_text,
      dueAt !== undefined ? dueAt : asg.due_at,
      points !== undefined ? points : asg.points,
      submissionType ?? asg.submission_type,
      asg.id
    );
    return { ok: true, assignment: db.prepare('SELECT * FROM assignment WHERE id = ?').get(asg.id) };
  });

  // Remove an assignment (cascades to its lessons/blocks/answers/attachments)
  app.delete('/assignments/:id', async (req, reply) => {
    const info = db.prepare('DELETE FROM assignment WHERE id = ?').run(req.params.id);
    if (info.changes === 0) return reply.code(404).send({ error: 'assignment not found' });
    return { ok: true, deleted: Number(req.params.id) };
  });

  // --- Lessons + blocks ------------------------------------------------------
  app.get('/lessons/:id', async (req, reply) => {
    const lesson = db.prepare('SELECT * FROM lesson WHERE id = ?').get(req.params.id);
    if (!lesson) return reply.code(404).send({ error: 'lesson not found' });
    const blocks = db
      .prepare('SELECT * FROM lesson_block WHERE lesson_id = ? ORDER BY seq')
      .all(lesson.id)
      .map((b) => ({ id: b.id, seq: b.seq, type: b.type, payload: JSON.parse(b.payload_json) }));
    return { ...lesson, blocks };
  });

  // Save/append a student's answer for a block (scaffold_q / draft)
  app.post('/blocks/:id/answer', async (req, reply) => {
    const block = db.prepare('SELECT lb.*, l.assignment_id AS assignment_id FROM lesson_block lb JOIN lesson l ON l.id = lb.lesson_id WHERE lb.id = ?').get(req.params.id);
    if (!block) return reply.code(404).send({ error: 'block not found' });
    const content = String(req.body?.content ?? '');

    const existing = db.prepare('SELECT * FROM answer WHERE lesson_block_id = ?').get(block.id);
    if (existing) {
      db.prepare("UPDATE answer SET content_text = ?, updated_at = datetime('now') WHERE id = ?")
        .run(content, existing.id);
      return { ok: true, answerId: existing.id, updated: true };
    }
    const res = db.prepare(
      'INSERT INTO answer (lesson_block_id, assignment_id, content_text) VALUES (?, ?, ?)'
    ).run(block.id, block.assignment_id, content);
    return { ok: true, answerId: res.lastInsertRowid, updated: false };
  });

  // Mark a lesson done + bump today's streak
  app.post('/lessons/:id/complete', async (req, reply) => {
    const lesson = db.prepare('SELECT * FROM lesson WHERE id = ?').get(req.params.id);
    if (!lesson) return reply.code(404).send({ error: 'lesson not found' });
    db.prepare("UPDATE lesson SET status = 'done' WHERE id = ?").run(lesson.id);

    const today = new Date().toISOString().slice(0, 10);
    db.prepare(
      `INSERT INTO streak (date, completed_count) VALUES (?, 1)
       ON CONFLICT(date) DO UPDATE SET completed_count = completed_count + 1`
    ).run(today);
    return { ok: true };
  });

  // --- Compile (spine stub: assemble current answers + what's missing) -------
  app.get('/assignments/:id/compile', async (req, reply) => {
    const asg = db.prepare('SELECT * FROM assignment WHERE id = ?').get(req.params.id);
    if (!asg) return reply.code(404).send({ error: 'assignment not found' });

    // All answerable blocks (scaffold_q + draft) in lesson/seq order
    const blocks = db.prepare(
      `SELECT lb.id, lb.type, lb.payload_json, l.seq AS lesson_seq, lb.seq AS block_seq
         FROM lesson_block lb
         JOIN lesson l ON l.id = lb.lesson_id
        WHERE l.assignment_id = ? AND lb.type IN ('scaffold_q','draft')
        ORDER BY l.seq, lb.seq`
    ).all(asg.id);

    const parts = [];
    const missing = [];
    for (const b of blocks) {
      const ans = db.prepare('SELECT content_text FROM answer WHERE lesson_block_id = ?').get(b.id);
      const payload = JSON.parse(b.payload_json);
      const label = payload.instruction || payload.prompt || `Block ${b.id}`;
      if (ans && ans.content_text.trim()) {
        parts.push(`## ${label}\n\n${ans.content_text.trim()}\n`);
      } else {
        missing.push(label);
      }
    }

    const compiled =
      `# ${asg.title}\n\n` +
      parts.join('\n') +
      (missing.length ? `\n---\n### Still to do (${missing.length})\n` + missing.map((m) => `- ${m}`).join('\n') + '\n' : '');

    return {
      assignmentId: asg.id,
      title: asg.title,
      complete: missing.length === 0,
      missing,
      compiledText: compiled
    };
  });

  // --- Planner + reflow (SPEC §7, step 4) ------------------------------------
  // GET /plan returns scheduled days + the unscheduled backlog (interpretation b).
  app.get('/plan', async (req) => {
    const userId = resolveUserId(req);
    return getPlan(userId);
  });

  // (Re)generate the schedule from scratch. Use for first-plan and fall-behind reflow.
  app.post('/plan/reflow', async (req) => {
    const userId = resolveUserId(req);
    return generatePlan(userId);
  });

  // Unschedule one lesson -> it moves to the backlog. Touches only plan_entry;
  // the lesson + its answers are untouched (so compile still reports it "not done").
  app.delete('/plan/lessons/:lessonId', async (req) => {
    const ok = unscheduleLesson(req.params.lessonId);
    return { ok, action: 'unscheduled' };
  });

  // Reschedule a backlogged lesson back into the plan (the "reset" path).
  app.post('/plan/lessons/:lessonId/reschedule', async (req, reply) => {
    const userId = resolveUserId(req);
    const ok = rescheduleLesson(userId, req.params.lessonId);
    if (!ok) return reply.code(404).send({ error: 'lesson not found for this user' });
    return { ok, action: 'rescheduled' };
  });

  // Clear the entire schedule -> everything to backlog. (Confirm-gated in the UI.)
  app.delete('/plan', async (req) => {
    const userId = resolveUserId(req);
    const cleared = clearPlan(userId);
    return { ok: true, cleared, action: 'plan_cleared' };
  });
}
