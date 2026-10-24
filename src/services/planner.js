import { db } from '../db/index.js';

// Config (tunable). Anti-procrastination core (SPEC §7):
// schedule backward from due date, reserve a submission buffer, cap daily load.
const DAILY_CAP_MIN = Number(process.env.DAILY_CAP_MIN || 15);
const SUBMISSION_BUFFER_DAYS = Number(process.env.SUBMISSION_BUFFER_DAYS || 1);

const dayStr = (d) => d.toISOString().slice(0, 10);
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
function daysBetween(a, b) { return Math.round((b - a) / 86400000); }

/**
 * (Re)generate the schedule for a user's TODO lessons.
 * Deterministic. Works backward from each assignment's due date, reserving a
 * submission buffer, distributing lessons across available days without
 * exceeding the daily cap where possible. Over-capacity days are flagged, not
 * silently crammed. Lessons that cannot fit land in `overflow` (and stay
 * UNSCHEDULED — i.e. in the backlog).
 *
 * Only touches plan_entry rows. Never touches lessons or answers.
 */
export function generatePlan(userId) {
  const lessons = db.prepare(
    `SELECT l.id AS lessonId, l.title, l.est_minutes AS estMinutes, l.status,
            a.id AS assignmentId, a.title AS assignment, a.due_at AS dueAt
       FROM lesson l
       JOIN assignment a ON a.id = l.assignment_id
       JOIN course c ON c.id = a.course_id
      WHERE c.user_id = ? AND l.status = 'todo'
      ORDER BY a.due_at IS NULL, a.due_at, l.seq`
  ).all(userId);

  const version = (db.prepare('SELECT MAX(reflow_version) AS v FROM plan_entry').get()?.v || 0) + 1;

  // Clear existing schedule for this user's lessons, then recompute.
  const clearStmt = db.prepare('DELETE FROM plan_entry WHERE lesson_id = ?');
  const insStmt = db.prepare(
    'INSERT INTO plan_entry (lesson_id, scheduled_date, reflow_version) VALUES (?, ?, ?)'
  );

  const today = new Date(dayStr(new Date()));
  const dayLoad = new Map(); // 'YYYY-MM-DD' -> minutes already placed
  const overflow = [];

  const tx = db.transaction(() => {
    for (const l of lessons) clearStmt.run(l.lessonId);

    for (const l of lessons) {
      // Determine the window: [today, lastAllowedDay]
      let lastAllowed;
      if (l.dueAt) {
        const due = new Date(l.dueAt.slice(0, 10));
        lastAllowed = addDays(due, -SUBMISSION_BUFFER_DAYS); // never on/after due
      } else {
        lastAllowed = addDays(today, 14); // no due date -> 2-week soft horizon
      }
      if (lastAllowed < today) lastAllowed = today; // overdue: schedule ASAP (today)

      // Earliest-fit: walk days from today forward, place on first day with room.
      let placed = false;
      const span = Math.max(0, daysBetween(today, lastAllowed));
      for (let i = 0; i <= span; i++) {
        const d = dayStr(addDays(today, i));
        const load = dayLoad.get(d) || 0;
        if (load + l.estMinutes <= DAILY_CAP_MIN) {
          insStmt.run(l.lessonId, d, version);
          dayLoad.set(d, load + l.estMinutes);
          placed = true;
          break;
        }
      }
      // Couldn't fit under the cap anywhere in the window -> overflow.
      // Place it on the last allowed day (flagged over-capacity) so it's still
      // scheduled and visible, rather than silently dropped.
      if (!placed) {
        const d = dayStr(lastAllowed);
        const load = dayLoad.get(d) || 0;
        insStmt.run(l.lessonId, d, version);
        dayLoad.set(d, load + l.estMinutes);
        overflow.push({ lessonId: l.lessonId, assignment: l.assignment, reason: 'over_capacity' });
      }
    }
  });
  tx();

  return getPlan(userId, { version, overflow });
}

/** Read the current plan: scheduled days + the unscheduled backlog. */
export function getPlan(userId, meta = {}) {
  const today = dayStr(new Date());

  // Scheduled lessons (have a plan_entry), grouped by date.
  const scheduled = db.prepare(
    `SELECT pe.scheduled_date AS date, l.id AS lessonId, l.title, l.est_minutes AS estMinutes,
            l.status, a.title AS assignment, a.due_at AS dueAt
       FROM plan_entry pe
       JOIN lesson l ON l.id = pe.lesson_id
       JOIN assignment a ON a.id = l.assignment_id
       JOIN course c ON c.id = a.course_id
      WHERE c.user_id = ?
      ORDER BY pe.scheduled_date, l.seq`
  ).all(userId);

  // Backlog: this user's TODO lessons with NO plan_entry (unscheduled).
  const backlog = db.prepare(
    `SELECT l.id AS lessonId, l.title, l.est_minutes AS estMinutes,
            a.title AS assignment, a.due_at AS dueAt
       FROM lesson l
       JOIN assignment a ON a.id = l.assignment_id
       JOIN course c ON c.id = a.course_id
      WHERE c.user_id = ? AND l.status = 'todo'
        AND l.id NOT IN (SELECT lesson_id FROM plan_entry)
      ORDER BY a.due_at IS NULL, a.due_at, l.seq`
  ).all(userId);

  // Group scheduled into days.
  const byDate = new Map();
  for (const s of scheduled) {
    if (!byDate.has(s.date)) byDate.set(s.date, []);
    byDate.get(s.date).push(s);
  }
  const days = [...byDate.entries()].map(([date, lessons]) => {
    const loadMinutes = lessons.reduce((sum, l) => sum + l.estMinutes, 0);
    return { date, loadMinutes, overCapacity: loadMinutes > DAILY_CAP_MIN, lessons };
  });

  const warnings = [];
  for (const d of days) {
    if (d.overCapacity) warnings.push({ type: 'over_capacity', date: d.date, message: `${d.date} is over the ${DAILY_CAP_MIN}-min daily cap — start earlier.` });
  }

  const streakRow = db.prepare('SELECT completed_count FROM streak WHERE date = ?').get(today);

  return {
    reflowVersion: meta.version ?? (db.prepare('SELECT MAX(reflow_version) AS v FROM plan_entry').get()?.v || 0),
    today,
    todayStreak: streakRow?.completed_count ?? 0,
    dailyCapMin: DAILY_CAP_MIN,
    submissionBufferDays: SUBMISSION_BUFFER_DAYS,
    days,
    unscheduled: backlog,           // the visible "backlog" (interpretation b)
    overflow: meta.overflow ?? [],
    warnings,
  };
}

/** Unschedule one lesson (-> backlog). Touches only plan_entry. */
export function unscheduleLesson(lessonId) {
  const info = db.prepare('DELETE FROM plan_entry WHERE lesson_id = ?').run(lessonId);
  return info.changes > 0;
}

/** Reschedule one backlogged lesson back into the plan (earliest-fit). */
export function rescheduleLesson(userId, lessonId) {
  const l = db.prepare(
    `SELECT l.id AS lessonId, l.est_minutes AS estMinutes, a.due_at AS dueAt
       FROM lesson l JOIN assignment a ON a.id = l.assignment_id
       JOIN course c ON c.id = a.course_id
      WHERE l.id = ? AND c.user_id = ?`
  ).get(lessonId, userId);
  if (!l) return false;

  // Remove any existing entry, then earliest-fit place it.
  db.prepare('DELETE FROM plan_entry WHERE lesson_id = ?').run(lessonId);

  const today = new Date(dayStr(new Date()));
  let lastAllowed = l.dueAt ? addDays(new Date(l.dueAt.slice(0, 10)), -SUBMISSION_BUFFER_DAYS) : addDays(today, 14);
  if (lastAllowed < today) lastAllowed = today;

  // current loads
  const loads = new Map();
  for (const row of db.prepare(
    `SELECT pe.scheduled_date d, SUM(l2.est_minutes) m
       FROM plan_entry pe JOIN lesson l2 ON l2.id = pe.lesson_id
       JOIN assignment a ON a.id = l2.assignment_id JOIN course c ON c.id = a.course_id
      WHERE c.user_id = ? GROUP BY pe.scheduled_date`
  ).all(userId)) loads.set(row.d, row.m || 0);

  const version = (db.prepare('SELECT MAX(reflow_version) AS v FROM plan_entry').get()?.v || 0);
  const span = Math.max(0, daysBetween(today, lastAllowed));
  for (let i = 0; i <= span; i++) {
    const d = dayStr(addDays(today, i));
    if ((loads.get(d) || 0) + l.estMinutes <= DAILY_CAP_MIN) {
      db.prepare('INSERT INTO plan_entry (lesson_id, scheduled_date, reflow_version) VALUES (?, ?, ?)')
        .run(lessonId, d, version);
      return true;
    }
  }
  // no room under cap -> place on last allowed day (over capacity, but scheduled)
  db.prepare('INSERT INTO plan_entry (lesson_id, scheduled_date, reflow_version) VALUES (?, ?, ?)')
    .run(lessonId, dayStr(lastAllowed), version);
  return true;
}

/** Clear the entire schedule for a user (-> everything to backlog). */
export function clearPlan(userId) {
  const info = db.prepare(
    `DELETE FROM plan_entry WHERE lesson_id IN (
       SELECT l.id FROM lesson l JOIN assignment a ON a.id = l.assignment_id
       JOIN course c ON c.id = a.course_id WHERE c.user_id = ?)`
  ).run(userId);
  return info.changes;
}
