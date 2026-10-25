"""Deterministic offline AI mocks for the lesson engine.

Preserves the app's run-anywhere-offline philosophy: with NO GEMINI_API_KEY
(or USE_MOCK_INTEGRATIONS on), decompose produces a real staged lesson, and
the Coach tutor + per-stage feedback produce warm, on-persona text — all
WITHOUT a network call. The anti-copy-paste rule is honored verbatim: the mock
Coach never writes the student's answer, it only guides.
"""
from __future__ import annotations


def mock_decompose(assignment: dict, styles: list[str], notes: str) -> dict:
    """Build a plausible 2-lesson decomposition grounded in the assignment.

    Mirrors the JS decompose schema: lessons[].blocks[] with the five block
    types (video, excerpt, scaffold_q, draft, flashcards). Style preferences
    nudge which block types appear first but every lesson stays ~10-15 min.
    """
    title = assignment.get("title", "this assignment")
    kind = assignment.get("kind", "assignment")
    topic = title

    kinesthetic_first = "kinesthetic" in styles
    reading_first = "reading" in styles

    lesson1_blocks = [
        {"type": "video", "videoQuery": f"{topic} explained for beginners"},
        {"type": "excerpt", "excerptTopic": topic},
        {
            "type": "scaffold_q",
            "prompt": f"In your own words, what is '{title}' really asking you to do?",
            "hint": "Restate the goal in one sentence and name the deliverable.",
        },
        {
            "type": "flashcards",
            "cards": [
                {"front": f"What is the core concept behind {topic}?",
                 "back": "The main idea the assignment is testing."},
                {"front": "What is the deliverable you must produce?",
                 "back": "The specific artifact the prompt asks for."},
                {"front": "What is one constraint or requirement to respect?",
                 "back": "A rule from the prompt or rubric you must follow."},
            ],
        },
    ]

    lesson2_blocks = [
        {
            "type": "scaffold_q",
            "prompt": f"Outline the steps you'll take to complete '{title}'.",
            "hint": "Think milestones: understand, plan, draft, review.",
        },
        {
            "type": "draft",
            "instruction": (
                f"Write your own first piece of the deliverable for '{title}'. "
                "Just get your real ideas down — you'll refine them."
            ),
            "rubricHint": "Address the main requirement from the prompt directly.",
        },
    ]

    if kinesthetic_first:
        # Learn-by-doing: pull the draft earlier.
        lesson1_blocks.append(lesson2_blocks.pop(1))
    if reading_first:
        lesson1_blocks.insert(0, {"type": "excerpt", "excerptTopic": f"{topic} fundamentals"})

    verb = "prepare for" if kind in {"exam", "quiz", "test"} else "tackle"
    return {
        "lessons": [
            {
                "title": f"Understand: {title}",
                "estMinutes": 12,
                "blocks": lesson1_blocks,
            },
            {
                "title": f"Apply & {verb}: {title}",
                "estMinutes": 13,
                "blocks": lesson2_blocks,
            },
        ]
    }


def mock_tutor_opening(lesson_title: str, styles: list[str]) -> str:
    style_hint = ""
    if "visual" in styles:
        style_hint = " Picture it as a quick sketch in your head."
    elif "kinesthetic" in styles:
        style_hint = " Let's learn it by trying, not just reading."
    return (
        f"Hey, great to see you! 👋 Today we're tackling \"{lesson_title}\" in small, "
        f"doable bites.{style_hint} First tiny step: in one sentence, what do you already "
        "know about this topic? Give it a shot!"
    )


def mock_tutor_reply(message: str) -> str:
    low = message.lower()
    if any(p in low for p in ("just give", "answer", "write it for me", "do it for me")):
        return (
            "I hear you, but I won't hand over the answer — that would rob you of the win. 💪 "
            "Instead, let's take one small step together: what's the very first thing the "
            "prompt is asking for? Tell me in a few words."
        )
    return (
        "Nice — I can see you're thinking it through! Here's a small push: can you add one "
        "concrete detail or example to what you just said? That's how we turn a good idea into "
        "your own solid answer. 🌱"
    )


def mock_challenge_feedback(challenge_kind: str, correct: bool | None) -> str:
    if challenge_kind == "flashcard":
        if correct:
            return "Yes! 🎉 You nailed the key idea there — that's exactly the recall we're building."
        return (
            "Not quite yet — close though! Think about the single most important word the "
            "concept hinges on, and give it another go. You've got this."
        )
    return (
        "Good thinking! 👏 I can see your reasoning. To push it one step further, try naming a "
        "specific example or detail that backs up your point. Keep it in your own words."
    )


def mock_draft_feedback() -> str:
    return (
        "Nice work getting a real draft down! 🙌 One thing you did well: you addressed the task "
        "head-on. One concrete improvement to try yourself: make your opening sentence state your "
        "main point more directly. I won't rewrite it — that's your voice. Give it a tweak!"
    )
