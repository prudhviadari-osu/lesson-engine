import { db } from '../db/index.js';

// Spine routes (SPEC §8). More arrive in later build steps:
// decompose, resources, planner/reflow, compile/consent, ingestion.
export async function registerRoutes(app) {
  // Health
  app.get('/health', async () => ({ ok: true, service: 'learning++', step: 'spine' }));

  // --- Courses + assignments -------------------------------------------------
  app.get('/courses', async () => {
    const courses = db.prepare('SELECT * FROM course ORDER BY id').all();
    const asgStmt = db.prepare('SELECT * FROM assignment WHERE course_id = ? ORDER BY id');
    return courses.map((c) => ({ ...c, assignments: asgStmt.all(c.id) }));
  });

  app.get('/assignments/:id', async (req, reply) => {
    const asg = db.prepare('SELECT * FROM assignment WHERE id = ?').get(req.params.id);
    if (!asg) return reply.code(404).send({ error: 'assignment not found' });
    const lessons = db.prepare('SELECT * FROM lesson WHERE assignment_id = ? ORDER BY seq').all(asg.id);
    return { ...asg, lessons };
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

  // --- Plan (spine stub: group today's todo lessons) -------------------------
  app.get('/plan', async () => {
    const today = new Date().toISOString().slice(0, 10);
    const lessons = db.prepare(
      `SELECT l.id AS lessonId, l.title, l.est_minutes AS estMinutes, a.title AS assignment
         FROM lesson l JOIN assignment a ON a.id = l.assignment_id
        WHERE l.status = 'todo' ORDER BY a.due_at, l.seq`
    ).all();
    const loadMinutes = lessons.reduce((s, l) => s + l.estMinutes, 0);
    const streakRow = db.prepare('SELECT completed_count FROM streak WHERE date = ?').get(today);
    return {
      reflowVersion: 1,
      today,
      todayStreak: streakRow?.completed_count ?? 0,
      days: [{ date: today, loadMinutes, overCapacity: loadMinutes > 15, lessons }],
      warnings: [],
      overflow: []
    };
  });
}
