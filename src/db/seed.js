// Seeds one fake, fully-decomposed assignment so the pipeline is demoable
// end-to-end with zero live API calls. (SPEC §10: demo-safety fixture.)
import { db, initSchema } from './index.js';

initSchema();

const reset = db.transaction(() => {
  // Clear everything (dev convenience — fresh seed each run)
  const tables = ['answer', 'plan_entry', 'lesson_block', 'lesson', 'attachment', 'assignment', 'course', 'streak', 'user'];
  for (const t of tables) db.prepare(`DELETE FROM ${t}`).run();
  // Reset AUTOINCREMENT counters so a fresh seed always yields stable IDs
  // (user 1, assignment 1, lesson 1, blocks 1-6) — keeps the harness/demo predictable.
  db.prepare(`DELETE FROM sqlite_sequence WHERE name IN (${tables.map(() => '?').join(',')})`).run(...tables);

  const user = db.prepare(
    `INSERT INTO user (display_name, learning_styles, learning_notes) VALUES (?, ?, ?)`
  ).run('Demo Student', JSON.stringify(['visual', 'kinesthetic']), 'I like real-world examples and learning by doing.');
  const userId = user.lastInsertRowid;

  const course = db.prepare(
    `INSERT INTO course (user_id, name, canvas_id) VALUES (?, ?, ?)`
  ).run(userId, 'Calculus I (demo)', 'demo-course-1');
  const courseId = course.lastInsertRowid;

  // Due 7 days from now, in local-ish ISO
  const due = new Date(Date.now() + 7 * 864e5).toISOString().slice(0, 10) + 'T23:59:00';

  const asg = db.prepare(
    `INSERT INTO assignment
       (course_id, title, description_text, due_at, points, submission_type, source, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(
    courseId,
    'Homework 4 — The Chain Rule',
    'Solve problems 1–5 from section 3.4. Show each differentiation step and explain where the chain rule applies.',
    due, 20, 'online_text_entry', 'paste', 'decomposed'
  );
  const asgId = asg.lastInsertRowid;

  const insLesson = db.prepare(
    `INSERT INTO lesson (assignment_id, seq, title, est_minutes, status) VALUES (?, ?, ?, ?, 'todo')`
  );
  const insBlock = db.prepare(
    `INSERT INTO lesson_block (lesson_id, seq, type, payload_json) VALUES (?, ?, ?, ?)`
  );

  // Lesson 1 — learn the concept
  const l1 = insLesson.run(asgId, 1, 'Understand the chain rule', 13).lastInsertRowid;
  insBlock.run(l1, 1, 'video', JSON.stringify({
    query: 'chain rule explained', videoId: 'dFvnbgIDwdo',
    title: 'The Chain Rule (demo fixture)', channel: 'Example Math',
    durationSec: 372, url: 'https://www.youtube.com/watch?v=dFvnbgIDwdo'
  }));
  insBlock.run(l1, 2, 'excerpt', JSON.stringify({
    attachmentId: null, page: 42, heading: '3.4 The Chain Rule',
    text: 'If a function is composed as f(g(x)), its derivative is f\u2019(g(x)) \u00b7 g\u2019(x). Differentiate the outer function, keep the inner intact, then multiply by the derivative of the inner function.'
  }));
  insBlock.run(l1, 3, 'scaffold_q', JSON.stringify({
    prompt: 'In your own words, when do you apply the chain rule?',
    hint: 'Think composite functions \u2014 a function inside another function.',
    savesTo: 'answer'
  }));
  insBlock.run(l1, 4, 'flashcards', JSON.stringify({
    cards: [
      { front: 'Chain rule formula?', back: "(f\u2218g)' = f'(g(x))\u00b7g'(x)" },
      { front: 'First step applying it?', back: 'Differentiate the outer function, leaving the inner unchanged.' }
    ]
  }));

  // Lesson 2 — do a piece of the real deliverable
  const l2 = insLesson.run(asgId, 2, 'Draft problem 1', 12).lastInsertRowid;
  insBlock.run(l2, 1, 'scaffold_q', JSON.stringify({
    prompt: 'Identify the outer and inner functions in problem 1.',
    hint: 'Rewrite it as f(g(x)) before differentiating.', savesTo: 'answer'
  }));
  insBlock.run(l2, 2, 'draft', JSON.stringify({
    instruction: 'Write your full solution to problem 1 using the chain rule.',
    rubricHint: 'Show each differentiation step.', savesTo: 'answer'
  }));

  console.log(`Seeded user ${userId} (Demo Student), course ${courseId}, assignment ${asgId} with 2 lessons.`);
});

reset();
db.close();
