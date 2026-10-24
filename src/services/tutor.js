import { generateText } from './gemini.js';
import { db } from '../db/index.js';

// Warm, lively temperature for the conversational turns. The structured JSON
// paths elsewhere stay precise; this one is intentionally chatty. Tune here.
const TUTOR_TEMPERATURE = Number(process.env.TUTOR_TEMPERATURE || 0.9);

const STYLE_GUIDANCE = {
  visual: 'This student leans VISUAL — paint quick mental pictures, describe diagrams, use spatial language ("picture the outer shell wrapped around the inner bit").',
  auditory: 'This student leans AUDITORY — talk it through like you are saying it out loud, use rhythm and little verbal mnemonics they could repeat.',
  reading: 'This student leans READING/WRITING — be precise with wording, offer crisp definitions, invite them to put things in writing.',
  kinesthetic: 'This student leans KINESTHETIC — get them DOING a tiny step immediately, learn-by-trying, concrete hands-on moves.',
};

function buildLearnerBlock(user) {
  if (!user) return '';
  const styles = Array.isArray(user.learningStyles) ? user.learningStyles : [];
  const styleLines = styles.map((s) => `- ${STYLE_GUIDANCE[s] || s}`).join('\n');
  const notes = (user.learningNotes || '').trim();
  if (!styles.length && !notes) return '';
  return `
WHO YOU ARE TUTORING (adapt tone + examples, never change the rules):
${styles.length ? styleLines : '- No stated learning-style preference; keep it balanced.'}
${notes ? `- The student also told us: "${notes}" — honor this.` : ''}`;
}

/**
 * The tutor persona + hard rules. Returned as a system instruction so it frames
 * EVERY turn without being re-sent as chat content.
 */
function buildSystemPrompt({ assignment, lesson, user }) {
  return `You are "Coach", the interactive tutor inside learning++. You are a BLEND of two things:
1) a warm, encouraging human tutor who chats naturally, and
2) a bite-size challenge GAME that gives instant, game-like feedback.

Your mission: actually TEACH this lesson's concept and guide the student to produce
the real deliverable IN THEIR OWN WORDS. You are the opposite of a copy-paste answer bot.

HARD RULES (never break these):
- NEVER write the student's answer, essay, or solution for them. Not even "as an example".
  If they ask you to "just give the answer", warmly refuse and turn it back into a small step they can do.
- Teach in SMALL bites: one idea or one question per turn. Never dump a wall of text.
- Always react to what the student ACTUALLY typed. If they are right, celebrate specifically
  (say WHAT was good). If they are off, don't just say "wrong" — nudge with a hint or a simpler
  sub-question so they can get there themselves.
- Keep each turn SHORT and lively (usually 2-5 sentences). Use the occasional emoji sparingly.
  End most turns with a single clear question or a tiny challenge for the student to attempt.
- Progressively steer toward the real deliverable. Once they understand the idea, have THEM
  draft the actual piece, then give feedback on their draft (praise + one concrete improvement).
- Stay on THIS lesson. Be honest if unsure; never invent fake facts.
${buildLearnerBlock(user)}

THE ASSIGNMENT (context — do not solve it for them):
Title: ${assignment?.title ?? 'unknown'}
Due: ${assignment?.due_at ?? 'unknown'} · Points: ${assignment?.points ?? 'unknown'}
Description: ${assignment?.description_text || assignment?.description_html || '(none provided)'}

THIS LESSON:
Title: ${lesson?.title ?? 'unknown'} (about ${lesson?.est_minutes ?? 10} minutes)

Stay in character as Coach for the whole conversation.`;
}

/** Fetch the lesson + its parent assignment, or throw NOT_FOUND. */
export function getLessonContext(lessonId) {
  const lesson = db.prepare('SELECT * FROM lesson WHERE id = ?').get(lessonId);
  if (!lesson) {
    const err = new Error('lesson not found');
    err.code = 'NOT_FOUND';
    throw err;
  }
  const assignment = db.prepare('SELECT * FROM assignment WHERE id = ?').get(lesson.assignment_id);
  return { lesson, assignment };
}

/** Transcript for a (lesson,user) session, oldest-first. */
export function getHistory(lessonId, userId) {
  const rows = db.prepare(
    `SELECT id, role, content, created_at FROM tutor_message
      WHERE lesson_id = ? AND (user_id IS ? OR user_id = ?)
      ORDER BY id`
  ).all(lessonId, userId ?? null, userId ?? null);
  return rows.map((r) => ({ id: r.id, role: r.role, content: r.content, createdAt: r.created_at }));
}

function insertMessage(lessonId, userId, role, content) {
  const res = db.prepare(
    'INSERT INTO tutor_message (lesson_id, user_id, role, content) VALUES (?, ?, ?, ?)'
  ).run(lessonId, userId ?? null, role, content);
  return res.lastInsertRowid;
}

/** Wipe a (lesson,user) session so the student can start over. */
export function resetSession(lessonId, userId) {
  const info = db.prepare(
    'DELETE FROM tutor_message WHERE lesson_id = ? AND (user_id IS ? OR user_id = ?)'
  ).run(lessonId, userId ?? null, userId ?? null);
  return info.changes;
}

// History in the shape generateText wants: { role, text }.
function toGeminiHistory(rows) {
  return rows.map((r) => ({ role: r.role === 'model' ? 'model' : 'user', text: r.content }));
}

/**
 * Start (or restart) a session: Coach speaks first with a warm hook + first
 * tiny challenge. If a session already exists and reset is false, returns the
 * existing history untouched (resume).
 */
export async function startSession(lessonId, user, { reset = false } = {}) {
  const userId = user?.id ?? null;
  const { lesson, assignment } = getLessonContext(lessonId);

  if (reset) resetSession(lessonId, userId);

  const existing = getHistory(lessonId, userId);
  if (existing.length && !reset) {
    return { lessonId: Number(lessonId), lessonTitle: lesson.title, resumed: true, history: existing };
  }

  const system = buildSystemPrompt({ assignment, lesson, user });
  // A hidden kickoff instruction — not stored as a student turn.
  const kickoff =
    'Begin the session. Greet the student warmly by energy (not a long intro), name what we are ' +
    'about to tackle in one friendly line, then teach the FIRST tiny idea and immediately hit them ' +
    'with one small question or micro-challenge to attempt. Keep it to 2-4 sentences.';

  const { text, modelUsed } = await generateText({
    prompt: kickoff,
    system,
    temperature: TUTOR_TEMPERATURE,
    history: [],
  });

  insertMessage(lessonId, userId, 'model', text);
  return {
    lessonId: Number(lessonId),
    lessonTitle: lesson.title,
    resumed: false,
    modelUsed,
    history: getHistory(lessonId, userId),
  };
}

/**
 * Send the student's message and get Coach's next turn. Persists both the
 * student's message and the tutor's reply so the session can resume later.
 */
export async function sendMessage(lessonId, user, message) {
  const userId = user?.id ?? null;
  const text = String(message ?? '').trim();
  if (!text) {
    const err = new Error('message is required');
    err.code = 'BAD_INPUT';
    throw err;
  }
  const { lesson, assignment } = getLessonContext(lessonId);

  const priorRows = getHistory(lessonId, userId);
  const system = buildSystemPrompt({ assignment, lesson, user });

  // Persist the student's turn first so it is not lost even if Gemini errors.
  insertMessage(lessonId, userId, 'user', text);

  const { text: reply, modelUsed } = await generateText({
    prompt: text,
    system,
    temperature: TUTOR_TEMPERATURE,
    history: toGeminiHistory(priorRows),
  });

  insertMessage(lessonId, userId, 'model', reply);
  return {
    lessonId: Number(lessonId),
    reply,
    modelUsed,
    history: getHistory(lessonId, userId),
  };
}
