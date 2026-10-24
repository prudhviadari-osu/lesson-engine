// Compile a student's own work into a submission-ready bundle (SPEC §5).
//
// Honesty-by-design: this reads the `answer` table only — the student's own
// writing from the staged flow / lesson player. It NEVER invents content. It
// reports exactly what's done and what's still missing, grouped by lesson, and
// gates "ready to submit" behind an explicit REVIEW + CONSENT step tied to a
// hash of the exact content the student approved (so editing an answer
// invalidates a prior consent — you can't consent once and keep changing it).

import { createHash } from 'node:crypto';
import { db } from '../db/index.js';

/**
 * Build the compiled submission for an assignment: assembled answers grouped by
 * lesson, a "what's left" breakdown (also grouped by lesson, flagging lessons
 * not yet started), the markdown bundle, a content hash, and the current
 * review/consent state (matched to that hash).
 */
export function compileAssignment(assignmentId, userId = null) {
  const asg = db.prepare('SELECT * FROM assignment WHERE id = ?').get(assignmentId);
  if (!asg) {
    const err = new Error('assignment not found');
    err.code = 'NOT_FOUND';
    throw err;
  }

  // Answerable blocks (scaffold_q = reflection, draft = deliverable) with their
  // lesson, in order. We separate "draft" (the real deliverable) from
  // "scaffold_q" (supporting reflection) in the output.
  const rows = db.prepare(
    `SELECT lb.id AS block_id, lb.type, lb.payload_json,
            l.id AS lesson_id, l.seq AS lesson_seq, l.title AS lesson_title
       FROM lesson_block lb
       JOIN lesson l ON l.id = lb.lesson_id
      WHERE l.assignment_id = ? AND lb.type IN ('scaffold_q','draft')
      ORDER BY l.seq, lb.seq`
  ).all(assignmentId);

  // Group by lesson, preserving order.
  const lessons = new Map();
  for (const r of rows) {
    if (!lessons.has(r.lesson_id)) {
      lessons.set(r.lesson_id, { lessonId: r.lesson_id, seq: r.lesson_seq, title: r.lesson_title, items: [] });
    }
    const ans = db.prepare('SELECT content_text FROM answer WHERE lesson_block_id = ?').get(r.block_id);
    const payload = JSON.parse(r.payload_json);
    const label = payload.instruction || payload.prompt || `Item ${r.block_id}`;
    const text = (ans?.content_text || '').trim();
    lessons.get(r.lesson_id).items.push({
      blockId: r.block_id,
      kind: r.type === 'draft' ? 'deliverable' : 'reflection',
      label,
      answer: text,
      done: text.length > 0,
    });
  }

  const lessonList = [...lessons.values()];

  // Totals + missing breakdown.
  const allItems = lessonList.flatMap((l) => l.items);
  const totalItems = allItems.length;
  const doneItems = allItems.filter((i) => i.done).length;
  const deliverables = allItems.filter((i) => i.kind === 'deliverable');
  const deliverablesDone = deliverables.filter((i) => i.done).length;

  const missingByLesson = lessonList
    .map((l) => ({
      lessonId: l.lessonId,
      title: l.title,
      lessonStarted: l.items.some((i) => i.done),
      missing: l.items.filter((i) => !i.done).map((i) => ({ kind: i.kind, label: i.label })),
    }))
    .filter((l) => l.missing.length > 0);

  const missingFlat = allItems.filter((i) => !i.done).map((i) => i.label);

  // --- Build the human-readable submission bundle (markdown) ---------------
  const lines = [];
  lines.push(`# ${asg.title}`);
  if (asg.due_at) lines.push(`_Due: ${asg.due_at}_`);
  lines.push('');
  lines.push(`> Compiled by learning++ from your own answers. ${doneItems}/${totalItems} items done` +
    (deliverables.length ? ` · ${deliverablesDone}/${deliverables.length} deliverable(s) drafted.` : '.'));
  lines.push('');

  for (const l of lessonList) {
    const done = l.items.filter((i) => i.done);
    if (!done.length) continue; // only show lessons with real content in the bundle
    lines.push(`## ${l.title}`);
    lines.push('');
    for (const it of done) {
      lines.push(`**${it.kind === 'deliverable' ? '✍️ ' : ''}${it.label}**`);
      lines.push('');
      lines.push(it.answer);
      lines.push('');
    }
  }

  if (missingByLesson.length) {
    lines.push('---');
    lines.push(`### Still to do (${missingFlat.length} item${missingFlat.length === 1 ? '' : 's'})`);
    lines.push('');
    for (const l of missingByLesson) {
      lines.push(`- **${l.title}**${l.lessonStarted ? '' : ' _(not started)_'}`);
      for (const m of l.missing) {
        lines.push(`  - ${m.kind === 'deliverable' ? '✍️ (deliverable) ' : ''}${m.label}`);
      }
    }
    lines.push('');
  }

  const compiledText = lines.join('\n');
  const contentHash = createHash('sha256').update(compiledText).digest('hex');

  // --- Review / consent state (tied to THIS content hash) ------------------
  const consentRow = db.prepare(
    `SELECT * FROM submission_consent
      WHERE assignment_id = ? AND (user_id IS ? OR user_id = ?)
      ORDER BY id DESC LIMIT 1`
  ).get(assignmentId, userId ?? null, userId ?? null);

  const consentValidForCurrent =
    !!consentRow && consentRow.content_hash === contentHash &&
    consentRow.reviewed === 1 && consentRow.consented === 1;

  const complete = missingFlat.length === 0;

  return {
    assignmentId: asg.id,
    title: asg.title,
    dueAt: asg.due_at,
    complete,
    totals: { totalItems, doneItems, deliverables: deliverables.length, deliverablesDone },
    byLesson: lessonList,
    missing: missingFlat,              // flat list (back-compat)
    missingByLesson,                   // richer, grouped
    compiledText,
    contentHash,
    review: {
      // Can the student submit? Only if they've reviewed + consented to THIS exact content.
      readyToSubmit: consentValidForCurrent,
      reviewed: !!consentRow && consentRow.content_hash === contentHash && consentRow.reviewed === 1,
      consented: !!consentRow && consentRow.content_hash === contentHash && consentRow.consented === 1,
      consentStale: !!consentRow && consentRow.content_hash !== contentHash, // answers changed since last consent
    },
  };
}

/**
 * Record the student's review + consent for the CURRENT compiled content.
 * The caller passes the contentHash they saw; if it no longer matches (they
 * edited an answer in between), we reject so consent can't drift from content.
 */
export function recordConsent(assignmentId, userId, { reviewed, consented, contentHash }) {
  const current = compileAssignment(assignmentId, userId);
  if (contentHash && contentHash !== current.contentHash) {
    const err = new Error('content changed since you reviewed it — please review the updated submission again');
    err.code = 'STALE_CONSENT';
    throw err;
  }
  db.prepare(
    `INSERT INTO submission_consent (assignment_id, user_id, content_hash, reviewed, consented)
     VALUES (?, ?, ?, ?, ?)`
  ).run(assignmentId, userId ?? null, current.contentHash, reviewed ? 1 : 0, consented ? 1 : 0);

  return compileAssignment(assignmentId, userId);
}
