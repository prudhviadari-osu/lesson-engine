import { db } from '../db/index.js';
import { findVideo } from './youtube.js';
import { findReading } from './reading.js';

/**
 * Resolve all unresolved resource blocks (video + excerpt) for an assignment:
 * video queries -> real YouTube results, excerpt topics -> PDF/Wikipedia text.
 * Idempotent: already-resolved blocks are skipped. (SPEC §11 step 3)
 */
export async function resolveResources(assignmentId) {
  const asg = db.prepare('SELECT id FROM assignment WHERE id = ?').get(assignmentId);
  if (!asg) {
    const err = new Error('assignment not found');
    err.code = 'NOT_FOUND';
    throw err;
  }

  const blocks = db.prepare(
    `SELECT lb.id, lb.type, lb.payload_json
       FROM lesson_block lb JOIN lesson l ON l.id = lb.lesson_id
      WHERE l.assignment_id = ? AND lb.type IN ('video','excerpt')
      ORDER BY l.seq, lb.seq`
  ).all(assignmentId);

  const update = db.prepare('UPDATE lesson_block SET payload_json = ? WHERE id = ?');
  let resolvedVideos = 0, resolvedReadings = 0, skipped = 0;

  for (const b of blocks) {
    const payload = JSON.parse(b.payload_json);
    if (payload.resolved === true) { skipped++; continue; }

    if (b.type === 'video') {
      const v = await findVideo(payload.query);
      if (v) { update.run(JSON.stringify({ ...payload, ...v }), b.id); if (v.resolved) resolvedVideos++; }
    } else if (b.type === 'excerpt') {
      const r = await findReading(payload.topic, assignmentId);
      if (r) { update.run(JSON.stringify({ ...payload, ...r }), b.id); if (r.resolved) resolvedReadings++; }
    }
  }

  return { assignmentId: Number(assignmentId), resolvedVideos, resolvedReadings, skipped, totalResourceBlocks: blocks.length };
}
