import { db } from '../db/index.js';

export const VALID_STYLES = ['visual', 'auditory', 'reading', 'kinesthetic'];
export const MAX_STYLES = 2;

/** Validate + normalize a learning_styles array. Throws on invalid input. */
export function validateStyles(styles) {
  if (styles == null) return [];
  if (!Array.isArray(styles)) {
    const e = new Error('learningStyles must be an array');
    e.code = 'BAD_INPUT';
    throw e;
  }
  const cleaned = [...new Set(styles.map((s) => String(s).toLowerCase().trim()))];
  for (const s of cleaned) {
    if (!VALID_STYLES.includes(s)) {
      const e = new Error(`invalid learning style "${s}". Allowed: ${VALID_STYLES.join(', ')}`);
      e.code = 'BAD_INPUT';
      throw e;
    }
  }
  if (cleaned.length > MAX_STYLES) {
    const e = new Error(`choose at most ${MAX_STYLES} learning styles (got ${cleaned.length})`);
    e.code = 'BAD_INPUT';
    throw e;
  }
  return cleaned;
}

function rowToUser(row) {
  if (!row) return null;
  return {
    id: row.id,
    displayName: row.display_name,
    learningStyles: JSON.parse(row.learning_styles || '[]'),
    learningNotes: row.learning_notes || '',
    createdAt: row.created_at,
  };
}

export function listUsers() {
  return db.prepare('SELECT * FROM user ORDER BY id').all().map(rowToUser);
}

export function getUser(id) {
  return rowToUser(db.prepare('SELECT * FROM user WHERE id = ?').get(id));
}

export function createUser({ displayName, learningStyles = [], learningNotes = '' }) {
  if (!displayName || !String(displayName).trim()) {
    const e = new Error('displayName is required');
    e.code = 'BAD_INPUT';
    throw e;
  }
  const styles = validateStyles(learningStyles);
  const res = db.prepare(
    'INSERT INTO user (display_name, learning_styles, learning_notes) VALUES (?, ?, ?)'
  ).run(String(displayName).trim(), JSON.stringify(styles), String(learningNotes || ''));
  return getUser(res.lastInsertRowid);
}

export function updateUser(id, { displayName, learningStyles, learningNotes }) {
  const existing = getUser(id);
  if (!existing) { const e = new Error('user not found'); e.code = 'NOT_FOUND'; throw e; }
  const name = displayName != null ? String(displayName).trim() : existing.displayName;
  const styles = learningStyles !== undefined ? validateStyles(learningStyles) : existing.learningStyles;
  const notes = learningNotes != null ? String(learningNotes) : existing.learningNotes;
  db.prepare('UPDATE user SET display_name = ?, learning_styles = ?, learning_notes = ? WHERE id = ?')
    .run(name, JSON.stringify(styles), notes, id);
  return getUser(id);
}

export function deleteUser(id) {
  const info = db.prepare('DELETE FROM user WHERE id = ?').run(id);
  return info.changes > 0;
}

/**
 * Resolve the acting user from the request (x-user-id header or ?userId=).
 * Falls back to the first user (the demo profile) so existing single-user
 * flows keep working without a frontend that sends identity yet.
 */
export function resolveUserId(req) {
  const fromHeader = req.headers['x-user-id'];
  const fromQuery = req.query?.userId;
  const raw = fromHeader ?? fromQuery;
  if (raw != null && String(raw).trim() !== '') {
    const u = getUser(Number(raw));
    if (u) return u.id;
  }
  const first = db.prepare('SELECT id FROM user ORDER BY id LIMIT 1').get();
  return first?.id ?? null;
}
