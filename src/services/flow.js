// Unified gamified STAGED LESSON FLOW.
//
// This is the MAIN way a lesson is "done": instead of a flat list of blocks, a
// lesson becomes an ordered pedagogical journey —
//   intro -> watch video(s) -> read excerpt(s) -> bite-size challenge(s)
//         -> draft the real deliverable -> complete
// Stages are DERIVED from the lesson's existing lesson_block rows at request
// time (no schema change to lesson_block). The static blocks + answer table +
// the "Coach" chat tutor all still exist underneath and feed this flow.
//
// Gamification lives in two additive tables (see db/schema.sql):
//   user_xp   — running total XP + the user's daily XP goal
//   xp_event  — one row per completed stage (idempotent via UNIQUE), doubles as
//               the stage-progress record and powers the daily-goal meter.
//
// Coach feedback (challenge/draft) reuses the tutor persona + generateText. It
// needs GEMINI_API_KEY; without it those calls throw err.code 'NO_API_KEY' and
// the routes map that to a graceful 400 (never a crash). Deriving the stages,
// reading progress, and awarding XP all work with NO live key.

import { db } from '../db/index.js';
import { generateText } from './gemini.js';
import { getLessonContext } from './tutor.js';

// --- Tuning dials -----------------------------------------------------------
// XP awarded for finishing each kind of stage. Intro/watch/read are small,
// challenges medium, the draft (the real work) largest, plus a completion bonus
// for finishing the whole lesson. Override via env to retune without code edits.
export const XP = {
  intro: Number(process.env.XP_INTRO || 5),
  video: Number(process.env.XP_VIDEO || 10),
  reading: Number(process.env.XP_READING || 10),
  challenge: Number(process.env.XP_CHALLENGE || 15),
  draft: Number(process.env.XP_DRAFT || 25),
  complete: Number(process.env.XP_COMPLETE || 20), // bonus for finishing the lesson
};

// Default daily XP goal for a new user (streak lives in its own table already).
export const DEFAULT_DAILY_GOAL = Number(process.env.DAILY_XP_GOAL || 50);

// Warmth for Coach's per-stage feedback. Matches the chat tutor's default feel.
const FEEDBACK_TEMPERATURE = Number(process.env.TUTOR_TEMPERATURE || 0.9);

const today = () => new Date().toISOString().slice(0, 10);

// --- Stage derivation -------------------------------------------------------

/**
 * Derive the ordered stage list for a lesson from its blocks. Pure DB read, no
 * live API calls. Order: intro -> videos -> readings -> challenges
 * (scaffold_q + flashcards) -> drafts -> complete. A lesson with no draft block
 * simply has no draft stage; the flow still works.
 *
 * Each stage: { key, type, title, xp, blockId?, payload? , prompt?, hint? }
 */
export function buildStages(lessonId) {
  const { lesson } = getLessonContext(lessonId); // throws NOT_FOUND
  const blocks = db
    .prepare('SELECT id, seq, type, payload_json FROM lesson_block WHERE lesson_id = ? ORDER BY seq')
    .all(lesson.id)
    .map((b) => ({ id: b.id, seq: b.seq, type: b.type, payload: JSON.parse(b.payload_json) }));

  const videos = blocks.filter((b) => b.type === 'video');
  const readings = blocks.filter((b) => b.type === 'excerpt');
  const challenges = blocks.filter((b) => b.type === 'scaffold_q' || b.type === 'flashcards');
  const drafts = blocks.filter((b) => b.type === 'draft');

  const stages = [];

  // Intro — a short "here's what we're doing" gateway. No block behind it.
  stages.push({
    key: 'intro',
    type: 'intro',
    title: `Let's start: ${lesson.title}`,
    xp: XP.intro,
    body: `You'll watch, read, try a quick challenge, then write a piece of the real deliverable. Small steps — let's go.`,
  });

  // Watch stage(s) — embed the resolved YouTube video right here.
  for (const b of videos) {
    stages.push({
      key: `video:${b.id}`,
      type: 'video',
      title: 'Watch',
      xp: XP.video,
      blockId: b.id,
      payload: b.payload, // { query, videoId, title, channel, url, embedUrl, thumbnail, resolved }
    });
  }

  // Read stage(s) — show the resolved excerpt right here.
  for (const b of readings) {
    stages.push({
      key: `reading:${b.id}`,
      type: 'reading',
      title: 'Read',
      xp: XP.reading,
      blockId: b.id,
      payload: b.payload, // { source, topic, heading, text, url, resolved }
    });
  }

  // Challenge stage(s) — bite-size questions with instant correct/try-again.
  for (const b of challenges) {
    if (b.type === 'flashcards') {
      // One challenge per card: recall the back; reveal-after-attempt is fine.
      const cards = Array.isArray(b.payload.cards) ? b.payload.cards : [];
      cards.forEach((card, i) => {
        stages.push({
          key: `flashcard:${b.id}:${i}`,
          type: 'challenge',
          challengeKind: 'flashcard',
          title: 'Challenge',
          xp: XP.challenge,
          blockId: b.id,
          prompt: card.front,
          answer: card.back, // reveal allowed after an attempt (factual recall)
          allowReveal: true,
        });
      });
    } else {
      // scaffold_q — the student writes in their own words; this SAVES to the
      // answer table (so compile sees it) via submitChallenge.
      stages.push({
        key: `challenge:${b.id}`,
        type: 'challenge',
        challengeKind: 'scaffold',
        title: 'Challenge',
        xp: XP.challenge,
        blockId: b.id,
        prompt: b.payload.prompt,
        hint: b.payload.hint || null,
        savesToAnswer: true,
        allowReveal: false, // never reveal — it's their own reasoning
      });
    }
  }

  // Draft stage(s) — the real deliverable. Saves to the answer table.
  for (const b of drafts) {
    stages.push({
      key: `draft:${b.id}`,
      type: 'draft',
      title: 'Draft the deliverable',
      xp: XP.draft,
      blockId: b.id,
      prompt: b.payload.instruction,
      rubricHint: b.payload.rubricHint || null,
      savesToAnswer: true,
      allowReveal: false, // Coach NEVER writes the student's answer
    });
  }

  // Complete — finishing stage (awards the completion bonus, marks lesson done).
  stages.push({
    key: 'complete',
    type: 'complete',
    title: 'Complete!',
    xp: XP.complete,
  });

  return { lesson, stages };
}

// --- XP + progress persistence ---------------------------------------------

/** Ensure a user_xp row exists; returns it. */
function ensureUserXp(userId) {
  if (userId == null) return { user_id: null, total_xp: 0, daily_goal: DEFAULT_DAILY_GOAL };
  let row = db.prepare('SELECT * FROM user_xp WHERE user_id = ?').get(userId);
  if (!row) {
    db.prepare('INSERT INTO user_xp (user_id, total_xp, daily_goal) VALUES (?, 0, ?)')
      .run(userId, DEFAULT_DAILY_GOAL);
    row = db.prepare('SELECT * FROM user_xp WHERE user_id = ?').get(userId);
  }
  return row;
}

/** Set of stage_keys this (user,lesson) has completed. */
function completedStageKeys(userId, lessonId) {
  const rows = db.prepare(
    'SELECT stage_key FROM xp_event WHERE (user_id IS ? OR user_id = ?) AND lesson_id = ?'
  ).all(userId ?? null, userId ?? null, lessonId);
  return new Set(rows.map((r) => r.stage_key));
}

/**
 * Award XP for finishing a stage, exactly once. Idempotent: if the stage is
 * already recorded, nothing changes and awarded:false is returned. Updates the
 * user's running total too. Returns { awarded, xp }.
 */
function awardStage(userId, lessonId, stageKey, xp) {
  const already = db.prepare(
    'SELECT id FROM xp_event WHERE (user_id IS ? OR user_id = ?) AND lesson_id = ? AND stage_key = ?'
  ).get(userId ?? null, userId ?? null, lessonId, stageKey);
  if (already) return { awarded: false, xp: 0 };

  const tx = db.transaction(() => {
    db.prepare(
      'INSERT INTO xp_event (user_id, lesson_id, stage_key, xp, date) VALUES (?, ?, ?, ?, ?)'
    ).run(userId ?? null, lessonId, stageKey, xp, today());
    if (userId != null) {
      ensureUserXp(userId);
      db.prepare(
        "UPDATE user_xp SET total_xp = total_xp + ?, updated_at = datetime('now') WHERE user_id = ?"
      ).run(xp, userId);
    }
  });
  tx();
  return { awarded: true, xp };
}

/** Gamification snapshot for a user: total XP, daily goal + today's progress. */
export function getGamificationState(userId) {
  const xpRow = ensureUserXp(userId);
  const todayXp = db.prepare(
    'SELECT COALESCE(SUM(xp), 0) AS s FROM xp_event WHERE (user_id IS ? OR user_id = ?) AND date = ?'
  ).get(userId ?? null, userId ?? null, today()).s;
  const streakRow = db.prepare('SELECT completed_count FROM streak WHERE date = ?').get(today());
  const dailyGoal = xpRow.daily_goal ?? DEFAULT_DAILY_GOAL;
  return {
    totalXp: xpRow.total_xp ?? 0,
    dailyGoal,
    dailyXp: todayXp,
    dailyGoalPct: dailyGoal > 0 ? Math.min(100, Math.round((todayXp / dailyGoal) * 100)) : 0,
    dailyGoalMet: todayXp >= dailyGoal,
    todayStreak: streakRow?.completed_count ?? 0,
  };
}

// --- Public: the staged flow + progress ------------------------------------

/**
 * Full staged flow for a lesson + this user's progress. No live API calls — safe
 * to call with GEMINI_API_KEY unset. Resource payloads (video/excerpt) are
 * surfaced INSIDE their stages so the UI embeds them in-flow (not as separate
 * blocks). `answer` on a flashcard stage is stripped unless the stage is already
 * done (reveal-after-attempt), so the harness can't leak factual answers early.
 */
export function getFlow(lessonId, user) {
  const userId = user?.id ?? null;
  const { lesson, stages } = buildStages(lessonId);
  const assignment = db.prepare('SELECT id, title FROM assignment WHERE id = ?').get(lesson.assignment_id);
  const done = completedStageKeys(userId, lesson.id);

  // Stages that count toward "finish the lesson" = everything except 'complete'.
  const workStages = stages.filter((s) => s.type !== 'complete');
  const doneWork = workStages.filter((s) => done.has(s.key)).length;
  const progressPct = workStages.length ? Math.round((doneWork / workStages.length) * 100) : 0;

  const publicStages = stages.map((s) => {
    const isDone = done.has(s.key);
    const out = {
      key: s.key,
      type: s.type,
      title: s.title,
      xp: s.xp,
      done: isDone,
    };
    if (s.blockId != null) out.blockId = s.blockId;
    if (s.body) out.body = s.body;
    if (s.payload) out.payload = s.payload;        // video/reading resource, embedded in-flow
    if (s.prompt) out.prompt = s.prompt;           // challenge/draft prompt
    if (s.hint) out.hint = s.hint;
    if (s.rubricHint) out.rubricHint = s.rubricHint;
    if (s.challengeKind) out.challengeKind = s.challengeKind;
    if (s.allowReveal) out.allowReveal = true;
    if (s.savesToAnswer) out.savesToAnswer = true;
    // Flashcard answer: only expose once the stage is done (reveal-after-attempt).
    if (s.challengeKind === 'flashcard' && isDone) out.answer = s.answer;
    // Prefill any saved answer text for challenge/draft stages (resume support).
    if (s.blockId != null && (s.type === 'challenge' || s.type === 'draft')) {
      const ans = db.prepare('SELECT content_text FROM answer WHERE lesson_block_id = ?').get(s.blockId);
      if (ans && ans.content_text) out.savedAnswer = ans.content_text;
    }
    return out;
  });

  return {
    lessonId: lesson.id,
    lessonTitle: lesson.title,
    lessonStatus: lesson.status,
    assignment: assignment ? { id: assignment.id, title: assignment.title } : null,
    stages: publicStages,
    progress: {
      stagesTotal: workStages.length,
      stagesDone: doneWork,
      progressPct,
      lessonComplete: lesson.status === 'done',
    },
    gamification: getGamificationState(userId),
  };
}

// --- Internal: find a stage by key (and its live payload) -------------------
function findStage(lessonId, stageKey) {
  const { stages } = buildStages(lessonId);
  const stage = stages.find((s) => s.key === stageKey);
  if (!stage) {
    const err = new Error(`stage "${stageKey}" not found in lesson ${lessonId}`);
    err.code = 'NOT_FOUND';
    throw err;
  }
  return stage;
}

// --- Public: advance a passive stage (intro / video / reading) --------------
/**
 * Mark a watch/read/intro stage done and award its XP. These have no answer to
 * check — finishing them IS the interaction (watched the video, read the text).
 */
export function advanceStage(lessonId, user, stageKey) {
  const userId = user?.id ?? null;
  const stage = findStage(lessonId, stageKey);
  if (!['intro', 'video', 'reading'].includes(stage.type)) {
    const err = new Error(`stage "${stageKey}" is a ${stage.type} stage — use the challenge/draft/complete endpoint`);
    err.code = 'BAD_INPUT';
    throw err;
  }
  const { awarded, xp } = awardStage(userId, lessonId, stage.key, stage.xp);
  return {
    ok: true,
    stageKey: stage.key,
    xpAwarded: awarded ? xp : 0,
    alreadyDone: !awarded,
    gamification: getGamificationState(userId),
  };
}

// --- Coach feedback helpers (reuse the tutor persona) -----------------------
import { getUser } from './users.js';

function styleLine(user) {
  const styles = Array.isArray(user?.learningStyles) ? user.learningStyles : [];
  const notes = (user?.learningNotes || '').trim();
  const bits = [];
  if (styles.length) bits.push(`They lean ${styles.join(' + ')} — adapt examples/tone to that.`);
  if (notes) bits.push(`They told us: "${notes}" — honor it.`);
  return bits.join(' ');
}

const COACH_RULES =
  'You are "Coach", a warm, encouraging bite-size tutor inside learning++. ' +
  'HARD RULE: never write the student\'s answer/solution/essay for them, not even "as an example" — ' +
  'if they ask, warmly refuse and give one tiny step they can take themselves. ' +
  'Keep it SHORT (2-4 sentences), lively, one idea at a time, sparing emoji.';

// --- Public: challenge submission (instant correct / try-again feedback) ----
/**
 * Student submits an answer to a CHALLENGE stage. Coach reacts with instant
 * "correct! / not quite, here's a nudge" feedback. For scaffold challenges we
 * also SAVE the student's words to the answer table (so compile sees them).
 *
 * XP is awarded when the attempt is judged correct (flashcards) OR when the
 * student has made a genuine attempt on a scaffold question (there's no single
 * right answer — the reward is for reasoning in their own words). Coach NEVER
 * reveals a scaffold answer; flashcard backs may be revealed after an attempt.
 *
 * Needs GEMINI_API_KEY for the feedback text — throws NO_API_KEY otherwise
 * (the route maps it to a graceful 400). Saving + XP for scaffold still happen
 * BEFORE the Gemini call so a missing key never loses the student's work.
 */
export async function submitChallenge(lessonId, user, stageKey, rawAnswer) {
  const userId = user?.id ?? null;
  const stage = findStage(lessonId, stageKey);
  if (stage.type !== 'challenge') {
    const err = new Error(`stage "${stageKey}" is not a challenge`);
    err.code = 'BAD_INPUT';
    throw err;
  }
  const answer = String(rawAnswer ?? '').trim();
  if (!answer) {
    const err = new Error('answer is required');
    err.code = 'BAD_INPUT';
    throw err;
  }

  const { lesson, assignment } = getLessonContext(lessonId);
  const fullUser = userId != null ? getUser(userId) : user;

  let correct = null; // null = "open" (scaffold); true/false for flashcards
  let xpResult = { awarded: false, xp: 0 };
  let revealed = null;

  if (stage.challengeKind === 'flashcard') {
    // Lightweight structured check: normalized token overlap with the known back.
    correct = looksCorrect(answer, stage.answer);
    if (correct) xpResult = awardStage(userId, lessonId, stage.key, stage.xp);
    if (stage.allowReveal) revealed = stage.answer; // reveal-after-attempt is fine
  } else {
    // scaffold_q: save the student's own words to the answer table (compile!).
    saveAnswerForBlock(stage.blockId, lesson.assignment_id, answer);
    // A genuine attempt earns the challenge XP (reasoning, not a lookup).
    xpResult = awardStage(userId, lessonId, stage.key, stage.xp);
  }

  // Coach's instant feedback (reacts to the ACTUAL answer). Needs a live key.
  const system = `${COACH_RULES} ${styleLine(fullUser)}`.trim();
  const prompt = buildChallengeFeedbackPrompt({ assignment, lesson, stage, answer, correct });
  const { text, modelUsed } = await generateText({
    prompt, system, temperature: FEEDBACK_TEMPERATURE, history: [],
  });

  return {
    ok: true,
    stageKey: stage.key,
    challengeKind: stage.challengeKind,
    correct,                 // true/false for flashcards; null for open scaffolds
    feedback: text,
    revealed,                // flashcard back, only after the attempt
    xpAwarded: xpResult.awarded ? xpResult.xp : 0,
    alreadyDone: !xpResult.awarded && (correct === true || stage.challengeKind !== 'flashcard'),
    savedToAnswer: stage.challengeKind !== 'flashcard',
    modelUsed,
    gamification: getGamificationState(userId),
  };
}

// --- Public: draft submission (save + Coach feedback, never rewrite) --------
/**
 * Student writes the real deliverable at a DRAFT stage. We SAVE it to the answer
 * table (so compile sees it + still reports it "not done" if left blank), then
 * Coach gives encouraging feedback + ONE concrete improvement. Coach never
 * rewrites it. XP is awarded for a genuine draft attempt. Needs a live key for
 * feedback; the save + XP happen first so no work is lost on NO_API_KEY.
 */
export async function submitDraft(lessonId, user, stageKey, rawContent) {
  const userId = user?.id ?? null;
  const stage = findStage(lessonId, stageKey);
  if (stage.type !== 'draft') {
    const err = new Error(`stage "${stageKey}" is not a draft`);
    err.code = 'BAD_INPUT';
    throw err;
  }
  const content = String(rawContent ?? '').trim();
  if (!content) {
    const err = new Error('draft content is required');
    err.code = 'BAD_INPUT';
    throw err;
  }

  const { lesson, assignment } = getLessonContext(lessonId);
  const fullUser = userId != null ? getUser(userId) : user;

  // Save the deliverable + award XP BEFORE the Gemini call (don't lose work).
  saveAnswerForBlock(stage.blockId, lesson.assignment_id, content);
  const xpResult = awardStage(userId, lessonId, stage.key, stage.xp);

  const system = `${COACH_RULES} ${styleLine(fullUser)}`.trim();
  const prompt =
    `The student just drafted their deliverable for this lesson. Give warm, specific feedback: ` +
    `name ONE thing they did well, then ONE concrete improvement they can make themselves. ` +
    `Do NOT rewrite it or supply the corrected version — nudge only.\n\n` +
    `Assignment: ${assignment?.title ?? 'unknown'}\n` +
    `Task: ${stage.prompt}\n` +
    (stage.rubricHint ? `Rubric hint: ${stage.rubricHint}\n` : '') +
    `\nStudent's draft:\n"""${content}"""`;
  const { text, modelUsed } = await generateText({
    prompt, system, temperature: FEEDBACK_TEMPERATURE, history: [],
  });

  return {
    ok: true,
    stageKey: stage.key,
    feedback: text,
    xpAwarded: xpResult.awarded ? xpResult.xp : 0,
    alreadyDone: !xpResult.awarded,
    savedToAnswer: true,
    modelUsed,
    gamification: getGamificationState(userId),
  };
}

// --- Public: complete the whole lesson --------------------------------------
/**
 * Finish the staged flow: mark the lesson done + bump the streak (reusing the
 * same behavior as POST /lessons/:id/complete) and award the completion bonus.
 * Idempotent for the bonus (won't double-count via xp_event UNIQUE), but we only
 * bump the streak the FIRST time the lesson transitions to done.
 */
export function completeFlow(lessonId, user) {
  const userId = user?.id ?? null;
  const { lesson } = getLessonContext(lessonId);

  const wasDone = lesson.status === 'done';
  const tx = db.transaction(() => {
    db.prepare("UPDATE lesson SET status = 'done' WHERE id = ?").run(lesson.id);
    if (!wasDone) {
      const d = today();
      db.prepare(
        `INSERT INTO streak (date, completed_count) VALUES (?, 1)
         ON CONFLICT(date) DO UPDATE SET completed_count = completed_count + 1`
      ).run(d);
    }
  });
  tx();

  const bonus = awardStage(userId, lessonId, 'complete', XP.complete);

  return {
    ok: true,
    lessonId: lesson.id,
    lessonComplete: true,
    firstCompletion: !wasDone,
    completionBonus: bonus.awarded ? bonus.xp : 0,
    gamification: getGamificationState(userId),
  };
}

// --- small helpers ----------------------------------------------------------

// Save/update a student's answer for a block (mirrors POST /blocks/:id/answer
// so compile reads it identically). Upserts on lesson_block_id.
function saveAnswerForBlock(blockId, assignmentId, content) {
  const existing = db.prepare('SELECT id FROM answer WHERE lesson_block_id = ?').get(blockId);
  if (existing) {
    db.prepare("UPDATE answer SET content_text = ?, updated_at = datetime('now') WHERE id = ?")
      .run(content, existing.id);
    return existing.id;
  }
  const res = db.prepare(
    'INSERT INTO answer (lesson_block_id, assignment_id, content_text) VALUES (?, ?, ?)'
  ).run(blockId, assignmentId, content);
  return res.lastInsertRowid;
}

// Normalize for a forgiving factual-recall comparison (flashcards only).
function normalize(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Lightweight "did they get the gist" check for flashcard recall. Correct if the
// normalized answer contains the key tokens of the known back (or vice-versa).
// Deliberately lenient — this is a confidence-builder, not an exam grader.
function looksCorrect(answer, known) {
  const a = normalize(answer);
  const k = normalize(known);
  if (!a || !k) return false;
  if (a.includes(k) || k.includes(a)) return true;
  const kTokens = [...new Set(k.split(' ').filter((w) => w.length > 2))];
  if (!kTokens.length) return false;
  const aSet = new Set(a.split(' '));
  const hit = kTokens.filter((t) => aSet.has(t)).length;
  return hit / kTokens.length >= 0.6;
}

function buildChallengeFeedbackPrompt({ assignment, lesson, stage, answer, correct }) {
  if (stage.challengeKind === 'flashcard') {
    return (
      `Quick recall challenge in the lesson "${lesson.title}".\n` +
      `Question: ${stage.prompt}\n` +
      `Expected idea: ${stage.answer}\n` +
      `Student answered: "${answer}"\n` +
      `They were judged ${correct ? 'CORRECT' : 'NOT QUITE'}. ` +
      (correct
        ? `Celebrate specifically what they nailed in one upbeat line.`
        : `Gently say "not quite" and give ONE small nudge toward the idea — do NOT state the full answer.`)
    );
  }
  // scaffold_q (open reasoning — never a single right answer; never reveal)
  return (
    `Open challenge in the lesson "${lesson.title}" (assignment: ${assignment?.title ?? 'unknown'}).\n` +
    `Prompt: ${stage.prompt}\n` +
    (stage.hint ? `Hint available: ${stage.hint}\n` : '') +
    `Student answered in their own words: "${answer}"\n` +
    `React to what they ACTUALLY wrote: if it's on track, celebrate the specific good part and ` +
    `push them one step further; if it's off, nudge with a hint or a simpler sub-question so they ` +
    `get there themselves. NEVER give them the answer outright.`
  );
}
