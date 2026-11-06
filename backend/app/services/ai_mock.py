"""Deterministic offline AI mocks for the lesson engine.

Preserves the app's run-anywhere-offline philosophy: with NO GEMINI_API_KEY
(or USE_MOCK_INTEGRATIONS on), decompose produces a real staged lesson, and
the Coach tutor + per-stage feedback produce warm, on-persona text — all
WITHOUT a network call. The anti-copy-paste rule is honored verbatim: the mock
Coach never writes the student's answer, it only guides.
"""
from __future__ import annotations


def _looks_like_number_systems(text: str) -> bool:
    t = (text or "").lower()
    hits = sum(k in t for k in (
        "base conversion", "base 2", "base 10", "binary", "hexadecimal",
        "2's complement", "two's complement", "1's complement", "base conversion",
        "ece 2060", "convert", "sign", "gray code",
    ))
    return hits >= 2


# A guiding video + excerpt reused across peaks (kept keyless-safe: resolve step
# turns these into real resources when a key is present; offline they show as
# "look this up" links, which is fine for the demo narrative).
def _video(q):
    return {"type": "video", "videoQuery": q}
def _excerpt(topic):
    return {"type": "excerpt", "excerptTopic": topic}
def _mcq(prompt, options, answer_index, explanation):
    return {"type": "mcq", "prompt": prompt, "options": options,
            "answerIndex": answer_index, "explanation": explanation}
def _numeric(prompt, answer, explanation, unit="", tolerance=0):
    return {"type": "numeric", "prompt": prompt, "answer": answer,
            "unit": unit, "tolerance": tolerance, "explanation": explanation}
def _fill(prompt, accepted, explanation):
    return {"type": "fill_blank", "prompt": prompt, "accepted": accepted, "explanation": explanation}
def _sa(prompt, hint=""):
    return {"type": "scaffold_q", "prompt": prompt, "hint": hint}
def _draft(instruction, rubric=""):
    return {"type": "draft", "instruction": instruction, "rubricHint": rubric}


def _mock_number_systems_lessons() -> dict:
    """Deep, mastery-style climb for ECE 2060 Problem 1 (number systems).

    Each lesson = one skill PEAK: teach -> a mastery check or two (mcq/short
    answer) -> the REAL homework problems as draft work -> next peak. The final
    lesson brings everything together into the submission. The 'draft' prompts
    are the ACTUAL assignment questions, verbatim, so the student does their
    real homework inside the tool (the whole point) with mastery scaffolding.
    """
    lessons = [
        # ---- Peak 1: Decimal -> Binary -----------------------------------
        {
            "title": "Peak 1 — Decimal → Binary",
            "estMinutes": 14,
            "blocks": [
                _video("convert decimal to binary repeated division method"),
                _excerpt("converting base 10 to base 2 by repeated division by 2"),
                _mcq(
                    "What's the cleanest method to convert a base-10 integer to base 2 by hand?",
                    ["Repeatedly divide by 2 and read the remainders bottom-to-top",
                     "Multiply the number by 2 until you reach 0",
                     "Subtract 10 repeatedly and count",
                     "Look it up in a times table"],
                    0,
                    "Repeated division by 2: each remainder is a binary digit, and you read them from LAST remainder to first (bottom-up)."),
                _mcq(
                    "Convert 13₁₀ to binary. 13 = 8+4+1. Which is correct?",
                    ["1101", "1011", "1110", "1001"],
                    0,
                    "13 = 1·8 + 1·4 + 0·2 + 1·1 = 1101₂. Check: 8+4+1 = 13. ✓"),
                _sa("In your own words, why do you read the remainders from bottom to top when dividing by 2?",
                    "Think about which remainder corresponds to the 1's place (the smallest power of 2)."),
                _numeric("Warm-up (auto-graded): convert 13₁₀ to binary. Type the bits only.",
                         "1101", "13 = 8+4+1 = 1101₂.", unit="(base 2)"),
                _fill("Fill in the blank: in repeated division by 2, the FIRST remainder you get is the ____ bit (the 1's place).",
                      ["last", "least significant", "lsb", "rightmost", "last one", "bottom"],
                      "The first remainder is the least-significant (rightmost) bit — which is why you read bottom-to-top."),
                _numeric("Quick check (auto-graded): what is 40₁₀ in binary? Type the bits.",
                         "101000", "40 = 32+8 = 101000₂.", unit="(base 2)"),
                _draft("HW 1-1.1 — Convert 79₁₀ to base 2. Show every division-by-2 step and the remainders, then write the final binary number.",
                       "Show all steps (repeated division), not just the answer — the rubric gives 0 for a right answer with the wrong/again missing approach."),
                _draft("HW 1-1.2 — Convert 40₁₀ to base 2. Show your work.",
                       "Show each division step and the remainder column."),
                _draft("HW 1-1.3 — Convert 4769₁₀ to base 2. Show your work.",
                       "This one is larger — keep your remainder column lined up so you don't drop a bit."),
            ],
        },
        # ---- Peak 2: Binary -> Decimal -----------------------------------
        {
            "title": "Peak 2 — Binary → Decimal",
            "estMinutes": 12,
            "blocks": [
                _excerpt("positional notation: converting base 2 to base 10 using powers of two"),
                _mcq(
                    "To convert a binary number to decimal, you…",
                    ["Multiply each bit by its power of 2 and sum them",
                     "Divide each bit by 2",
                     "Count the number of 1s",
                     "Reverse the digits"],
                    0,
                    "Each bit's place value is a power of 2 (…8,4,2,1). Multiply each bit by its place value and add."),
                _mcq(
                    "What is 1011₂ in base 10?",
                    ["11", "13", "9", "7"],
                    0,
                    "1·8 + 0·4 + 1·2 + 1·1 = 8+2+1 = 11."),
                _draft("HW 1-2.1 — Convert 10101011₂ to base 10. Show your work (write each power of 2 and the sum).",
                       "Line up each bit with its power of two; show the addition."),
                _draft("HW 1-2.2 — Convert 0100111011₂ to base 10. Show your work.",
                       "Watch the leading zero — it contributes 0 but keep your place values aligned."),
            ],
        },
        # ---- Peak 3: Other bases & hex -----------------------------------
        {
            "title": "Peak 3 — Other bases & hexadecimal",
            "estMinutes": 15,
            "blocks": [
                _video("convert decimal to hexadecimal and base 3 conversion"),
                _mcq(
                    "In hexadecimal, what decimal value does the digit 'E' represent?",
                    ["14", "15", "13", "11"],
                    0,
                    "Hex digits go 0-9 then A=10, B=11, C=12, D=13, E=14, F=15."),
                _sa("Explain how converting a fraction (like 0.27₁₀) to another base differs from converting the integer part.",
                    "Integer part: repeated division. Fraction part: repeated MULTIPLICATION by the base, reading the carries top-down."),
                _draft("HW 1-3.1 — Convert 211₃ to base 10. Show your work.",
                       "Use positional notation with powers of 3."),
                _draft("HW 1-3.2 — Convert DE3A₁₆ to base 10. Show your work.",
                       "D=13, E=14, A=10; multiply by powers of 16."),
                _draft("HW 1-3.3 — Convert 42855₁₀ to hexadecimal. Show your work.",
                       "Repeated division by 16; remainders 10-15 become A-F."),
                _draft("HW 1-3.4 — Convert 93.27₁₀ to base 4, to 10 places after the point. Show your work.",
                       "Integer part by division by 4; fractional part by repeated multiplication by 4."),
            ],
        },
        # ---- Peak 4: Binary arithmetic (add / subtract / multiply / divide)
        {
            "title": "Peak 4 — Binary arithmetic",
            "estMinutes": 16,
            "blocks": [
                _video("binary addition subtraction with carries and borrows"),
                _mcq(
                    "In binary addition, 1 + 1 = ?",
                    ["10 (0 carry 1)", "2", "11", "1"],
                    0,
                    "There's no digit '2' in binary: 1+1 = 10₂, i.e. write 0 and carry 1."),
                _mcq(
                    "When subtracting in binary and you compute 0 − 1 in a column, you…",
                    ["Borrow from the next higher column (it becomes 10₂ − 1 = 1)",
                     "Write 1 and carry 1",
                     "Write −1",
                     "Skip the column"],
                    0,
                    "Borrowing brings in a value of 2 (10₂) to that column, so 10₂ − 1 = 1, and the next column drops by 1."),
                _draft("HW 1-4 — Add these binary numbers directly in binary: (1) 1101₂ + 111₂, (2) 10001₂ + 10101₂, (3) 1011011₂ + 111111₂ + 1101₂. Show carries.",
                       "Keep carries visible above the columns; the rubric wants the approach shown."),
                _draft("HW 1-5 — Subtract the smaller from the larger, showing all borrows: (1) 111011₂ − 11111₂, (2) 101001₂ − 11101₂, (3) 100000₂ − 11011₂.",
                       "Mark each borrow clearly so the columns are identifiable."),
                _draft("HW 1-6 — Multiply in base 2, showing work: (1) 1101₂ × 11₂, (2) 1011₂ × 010₂, (3) 11011₂ × 1111₂.",
                       "Shift-and-add; align partial products by column."),
                _draft("HW 1-7 — Divide, showing columns; give binary quotient + remainder: (1) 11011₂ ÷ 111₂, (2) 10111₂ ÷ 101₂, (3) 1100101₂ ÷ 1011₂.",
                       "Long division in binary — keep the columns lined up."),
            ],
        },
        # ---- Peak 5: Negative numbers & complements ----------------------
        {
            "title": "Peak 5 — Negatives: sign-magnitude, 1's & 2's complement",
            "estMinutes": 16,
            "blocks": [
                _video("sign magnitude ones complement twos complement explained"),
                _excerpt("two's complement using N* = 2^n - N and the bit-flip shortcut"),
                _mcq(
                    "The quick 'shortcut' for 2's complement of a binary number is…",
                    ["Flip all bits, then add 1",
                     "Flip all bits only",
                     "Add 1 only",
                     "Reverse the digit order"],
                    0,
                    "2's complement = (1's complement) + 1 = flip every bit, then add 1. The formula N* = 2ⁿ − N gives the same result."),
                _mcq(
                    "In 5-bit sign-magnitude, how is the sign stored?",
                    ["The leftmost (MSB) bit: 0 = positive, 1 = negative",
                     "The rightmost bit",
                     "An extra decimal sign kept separately",
                     "There is no sign bit"],
                    0,
                    "Sign-magnitude uses the MSB purely as a sign flag; the remaining bits are the magnitude."),
                _sa("Why does −0 exist in sign-magnitude and 1's complement but NOT in 2's complement?",
                    "Think about how many bit patterns map to zero in each representation."),
                _draft("HW 1-8.1 — In 5-bit sign & magnitude, express: −13, +12, −7, −0, −16. Show your work.",
                       "MSB = sign; magnitude in the remaining 4 bits. Note which values even fit in n=5."),
                _draft("HW 1-8.2 — Using N* = 2ⁿ − N, express in 2's complement: −12 (n=5), −5 (n=5), +6 (n=7), 0 (n=7). Show your work.",
                       "Apply the formula explicitly; then sanity-check with the flip-and-add-1 shortcut."),
                _draft("HW 1-8.3 — Find the 2's complement of −13 and −7 (n=5) using the flip-bits shortcut, and EXPLAIN each step.",
                       "Explain, don't just state — the problem asks you to show you understand the shortcut."),
                _draft("HW 1-9 — 1's complement with N̄ = (2ⁿ−1) − N: (1) −48 (n=7) by formula, (2) −35 (n=7) by the flip shortcut, explaining your steps.",
                       "1's complement is just flipping the bits; show the formula gives the same bits."),
                _draft("HW 1-11 — Add these 2's-complement numbers (n=7), show work, and convert to base 10 to check: 1001101+0100101, 1001101+1010101, 1001110+0111101. Then repeat for the 1's-complement set in 1-11.2.",
                       "Add normally in binary; for 1's complement remember the end-around carry."),
            ],
        },
        # ---- Peak 6: Codes + bring it together ---------------------------
        {
            "title": "Peak 6 — Binary codes & final assembly",
            "estMinutes": 13,
            "blocks": [
                _mcq(
                    "What is the main advantage of Gray code for a counter?",
                    ["Only one bit changes between consecutive values (less switching → less power/error)",
                     "It uses fewer bits than binary",
                     "It is faster to add",
                     "It stores negative numbers"],
                    0,
                    "In Gray code successive values differ by exactly one bit, which reduces switching activity and transition glitches."),
                _mcq(
                    "What is the highest number representable with 7 bits (unsigned)?",
                    ["127", "128", "63", "255"],
                    0,
                    "7 bits → 2⁷ − 1 = 127 (all ones = 1111111₂)."),
                _draft("HW 1-10 — (1) For a counter 0→11, how much less power (%) does Gray code use vs plain binary? Explain. (2a) Highest value in 7 bits in base 10, (2b) in hex, (2c) that minus 1 in hex, (2d) that hex value as ASCII.",
                       "Count bit transitions for each coding to get the power comparison; show the hex/ASCII steps."),
                _draft("HW 1-10 fill-in — Complete the base-10 ↔ base-2 table for 0 through 16 and note the pattern you observe.",
                       "No work needed per the prompt, but write the pattern you notice (it's the point of the exercise)."),
                _sa("Bring it together: across this whole assignment, what single idea connects base conversion, binary arithmetic, and complements?",
                    "Think about positional value and how 'base' and 'number of bits' frame every one of these operations."),
            ],
        },
    ]
    return {"lessons": lessons}


def mock_decompose(assignment: dict, styles: list[str], notes: str) -> dict:
    """Build a plausible decomposition grounded in the assignment.

    PRINCIPLE: the lesson IS the real homework. The actual assignment questions
    are the spine (as 'draft' work stages, verbatim); AI mastery supplements
    (mcq + short-answer + a teaching video/excerpt) wrap around them only as
    needed, and the final lesson brings it together.

    For the ECE 2060 base-conversion / number-systems assignment we author a
    deep, mastery-style, multi-peak climb that contains the REAL problems. Any
    other assignment falls back to a solid generic structure.
    """
    title = assignment.get("title", "this assignment")
    kind = assignment.get("kind", "assignment")
    topic = title
    text = (assignment.get("description") or "") + " " + title

    # Deep hand-authored showcase for the number-systems assignment.
    if _looks_like_number_systems(text):
        return _mock_number_systems_lessons()
    return _mock_decompose_generic(assignment, styles, notes)


def _mock_decompose_generic(assignment, styles, notes):
    """Solid generic fallback for any assignment that isn't the showcase one.
    Still real-homework-first: a scaffold to restate the task, then a draft of
    the actual deliverable, with a teaching video/excerpt + an mcq check."""
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
    if challenge_kind in ("numeric", "fill_blank"):
        if correct:
            return "Spot on! ✅ Your answer checks out exactly — that's the method working. On to the next step. 🧗"
        return (
            "Not quite — close though. Re-trace the steps of the method (line them up carefully) and "
            "check your final value against each place; the explanation below shows the target. Give it another go!"
        )
    if challenge_kind == "mcq":
        if correct:
            return "Exactly right! ✅ You picked the option for the right reason — that's the idea locked in."
        return (
            "Not quite — but good attempt. Look at the explanation below and notice where the "
            "reasoning diverges; the correct option follows the method step-by-step. Try the next one! 🧗"
        )
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


# ------------------------------- portfolio ---------------------------------
def mock_portfolio_skills(work: list[dict]) -> dict:
    """Deterministic resume-worthy skills grounded in the student's completed work.

    Mirrors the JS skillsSchema: {skills:[{skill, evidence}]}. Each skill is tied
    to a concrete piece of work the student actually finished (honesty-by-design),
    so offline output still looks real and is stable for a given set of work.
    """
    skills: list[dict] = []
    seen: set[str] = set()

    def add(skill: str, evidence: str) -> None:
        key = skill.lower()
        if skill and key not in seen:
            seen.add(key)
            skills.append({"skill": skill, "evidence": evidence})

    for a in work:
        title = a.get("title") or "an assignment"
        course = a.get("course_code") or a.get("course_title") or "coursework"
        label = f'"{title}" ({course})'
        # Derive a couple of grounded skills per completed assignment.
        add(f"Applied {title}", f"Completed {label}")
        add("Technical problem solving", f"Worked through {label} step by step")

    # A few durable, cross-cutting skills any completed-work student can claim.
    if work:
        add("Self-directed learning", "Finished lessons independently in learning++")
        add("Written communication", "Drafted deliverables in their own words")
        add("Time management", "Completed coursework through staged daily lessons")
    return {"skills": skills}


def mock_portfolio_projects(skills: list[str], count: int) -> dict:
    """Deterministic portfolio-project recommendations built on the student's skills.

    Mirrors the JS projectsSchema: {projects:[{name, difficulty, description,
    skillsReinforced, newSkills, time}]}. Stable for a given skill set + count.
    """
    base = skills[:3] if skills else ["your coursework skills"]
    difficulties = ["Beginner", "Intermediate", "Advanced"]
    times = ["1 week", "2 weeks", "3 weeks", "1 month", "1 month"]
    templates = [
        ("Interactive CLI toolkit", "A command-line tool that automates a repetitive task, with tests and a README."),
        ("Full-stack study tracker", "A small web app that stores and visualizes your study progress over time."),
        ("Data-analysis mini project", "Load a public dataset, clean it, and surface three insights with charts."),
        ("REST API with auth", "A small service exposing CRUD endpoints behind token-based authentication."),
        ("Algorithms playground", "Implement and benchmark a few classic algorithms with clear write-ups."),
        ("Portfolio website", "A personal site that showcases your completed projects and skills."),
    ]
    new_skill_pool = ["Testing", "Git workflow", "API design", "Data visualization",
                      "Deployment", "Documentation"]

    n = max(1, min(count, len(templates)))
    projects = []
    for i in range(n):
        name, desc = templates[i]
        projects.append({
            "name": name,
            "difficulty": difficulties[i % len(difficulties)],
            "description": desc,
            "skillsReinforced": base,
            "newSkills": [new_skill_pool[i % len(new_skill_pool)],
                          new_skill_pool[(i + 1) % len(new_skill_pool)]],
            "time": times[i % len(times)],
        })
    return {"projects": projects}
