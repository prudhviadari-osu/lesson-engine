import { Type } from '@google/genai';
import { generateJSON } from './gemini.js';
import { db } from '../db/index.js';

// Structured-output schema: Gemini MUST return exactly this shape.
const lessonSchema = {
  type: Type.OBJECT,
  properties: {
    lessons: {
      type: Type.ARRAY,
      description: 'Ordered mini-lessons, each ~10-15 minutes.',
      items: {
        type: Type.OBJECT,
        properties: {
          title: { type: Type.STRING },
          estMinutes: { type: Type.INTEGER },
          blocks: {
            type: Type.ARRAY,
            items: {
              type: Type.OBJECT,
              properties: {
                type: {
                  type: Type.STRING,
                  enum: ['video', 'excerpt', 'scaffold_q', 'draft', 'flashcards'],
                },
                // video
                videoQuery: { type: Type.STRING, description: 'Search phrase for a teaching video (type=video only).' },
                // excerpt
                excerptTopic: { type: Type.STRING, description: 'Topic/section to pull from the textbook (type=excerpt only).' },
                // scaffold_q
                prompt: { type: Type.STRING, description: 'Question for the student to answer (type=scaffold_q).' },
                hint: { type: Type.STRING },
                // draft
                instruction: { type: Type.STRING, description: 'Instruction to write a piece of the real deliverable (type=draft).' },
                rubricHint: { type: Type.STRING },
                // flashcards
                cards: {
                  type: Type.ARRAY,
                  items: {
                    type: Type.OBJECT,
                    properties: { front: { type: Type.STRING }, back: { type: Type.STRING } },
                    propertyOrdering: ['front', 'back'],
                  },
                },
              },
              propertyOrdering: ['type', 'videoQuery', 'excerptTopic', 'prompt', 'hint', 'instruction', 'rubricHint', 'cards'],
            },
          },
        },
        propertyOrdering: ['title', 'estMinutes', 'blocks'],
      },
    },
  },
  propertyOrdering: ['lessons'],
};

function buildPrompt(assignment) {
  return `You are the lesson designer for "learning++", a study tool whose PURPOSE is to make
students genuinely learn their coursework in small daily chunks — the OPPOSITE of
copy-pasting an AI answer. You break an assignment into a sequence of ~10-15 minute
mini-lessons a busy student can do on the go.

STRICT RULES:
- NEVER write the student's answer or the deliverable for them. "draft" blocks give an
  INSTRUCTION for the student to write their OWN work; never include a model answer.
- Break the assignment down as finely as it allows. A large assignment = more lessons.
- Each lesson is one sitting of ~10-15 minutes. Order them so earlier lessons teach the
  concept and later lessons apply it to produce pieces of the actual deliverable.
- Block types and when to use them:
  * "video": a short teaching video. Provide "videoQuery" — a precise YouTube search phrase
    for the specific concept (not the whole assignment).
  * "excerpt": a reading from the student's own textbook. Provide "excerptTopic" — the
    section/topic to locate. (The system matches it to the uploaded PDF later.)
  * "scaffold_q": a short comprehension/thinking question. Provide "prompt" and optional "hint".
    The student writes the answer; it is saved toward their understanding.
  * "draft": the student writes a real piece of the deliverable. Provide "instruction" and an
    optional "rubricHint". These accumulate into the final submission.
  * "flashcards": 3-6 recall cards. Provide "cards" as {front, back} pairs grounded in the material.
- Early lessons: mostly video + excerpt + scaffold_q + flashcards (learning).
- Later lessons: mostly scaffold_q + draft (applying + producing their own work).
- Keep it realistic and encouraging. Front-load learning so the final drafts are the student's
  own, well-understood work.

ASSIGNMENT:
Title: ${assignment.title}
Points: ${assignment.points ?? 'unknown'}
Submission type: ${assignment.submission_type ?? 'unknown'}
Due: ${assignment.due_at ?? 'unknown'}

Description:
${assignment.description_text || assignment.description_html || '(no description provided)'}

Produce the lessons now.`;
}

/**
 * Decompose an assignment (by id) into lessons + blocks, persisting them.
 * Replaces any existing lessons for that assignment (idempotent re-decompose).
 * Returns the created lessons with blocks.
 */
export async function decomposeAssignment(assignmentId) {
  const assignment = db.prepare('SELECT * FROM assignment WHERE id = ?').get(assignmentId);
  if (!assignment) {
    const err = new Error('assignment not found');
    err.code = 'NOT_FOUND';
    throw err;
  }

  const { data, cached } = await generateJSON({
    prompt: buildPrompt(assignment),
    schema: lessonSchema,
    cacheKeyExtra: `decompose:${assignmentId}`,
  });

  const lessons = Array.isArray(data?.lessons) ? data.lessons : [];
  if (lessons.length === 0) {
    const err = new Error('Gemini returned no lessons.');
    err.raw = JSON.stringify(data);
    throw err;
  }

  // Persist in a transaction: wipe old lessons for this assignment, insert new.
  const persist = db.transaction(() => {
    db.prepare('DELETE FROM lesson WHERE assignment_id = ?').run(assignmentId);

    const insLesson = db.prepare(
      'INSERT INTO lesson (assignment_id, seq, title, est_minutes, status) VALUES (?, ?, ?, ?, \'todo\')'
    );
    const insBlock = db.prepare(
      'INSERT INTO lesson_block (lesson_id, seq, type, payload_json) VALUES (?, ?, ?, ?)'
    );

    lessons.forEach((lesson, li) => {
      const estMinutes = clampMinutes(lesson.estMinutes);
      const lessonId = insLesson.run(assignmentId, li + 1, lesson.title || `Lesson ${li + 1}`, estMinutes).lastInsertRowid;
      const blocks = Array.isArray(lesson.blocks) ? lesson.blocks : [];
      blocks.forEach((b, bi) => {
        insBlock.run(lessonId, bi + 1, b.type, JSON.stringify(normalizeBlock(b)));
      });
    });

    db.prepare("UPDATE assignment SET status = 'decomposed' WHERE id = ?").run(assignmentId);
  });
  persist();

  const out = db.prepare('SELECT * FROM lesson WHERE assignment_id = ? ORDER BY seq').all(assignmentId);
  const blockStmt = db.prepare('SELECT id, seq, type, payload_json FROM lesson_block WHERE lesson_id = ? ORDER BY seq');
  const withBlocks = out.map((l) => ({
    ...l,
    blocks: blockStmt.all(l.id).map((b) => ({ id: b.id, seq: b.seq, type: b.type, payload: JSON.parse(b.payload_json) })),
  }));

  return { cached, lessonCount: withBlocks.length, lessons: withBlocks };
}

function clampMinutes(m) {
  const n = Number(m);
  if (!Number.isFinite(n)) return 12;
  return Math.min(20, Math.max(5, Math.round(n)));
}

// Convert Gemini's flat block into our stored payload shape (SPEC §6).
// Resource-bearing blocks (video/excerpt) store the AI's *request* now; Step 3
// fills in actual videoId / excerpt text via YouTube + PDF matching.
function normalizeBlock(b) {
  switch (b.type) {
    case 'video':
      return { query: b.videoQuery || '', videoId: null, title: null, channel: null, durationSec: null, url: null, resolved: false };
    case 'excerpt':
      return { topic: b.excerptTopic || '', attachmentId: null, page: null, heading: null, text: null, resolved: false };
    case 'scaffold_q':
      return { prompt: b.prompt || '', hint: b.hint || '', savesTo: 'answer' };
    case 'draft':
      return { instruction: b.instruction || '', rubricHint: b.rubricHint || '', savesTo: 'answer' };
    case 'flashcards':
      return { cards: Array.isArray(b.cards) ? b.cards.map((c) => ({ front: c.front || '', back: c.back || '' })) : [] };
    default:
      return {};
  }
}
