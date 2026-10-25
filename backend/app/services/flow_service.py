"""Unified gamified STAGED LESSON FLOW (ported from flow.js).

A lesson becomes an ordered pedagogical journey derived from its blocks:
  intro -> watch video(s) -> read excerpt(s) -> bite-size challenge(s)
        -> draft the real deliverable -> complete
XP is awarded per completed stage (idempotent via xp_events UNIQUE), progress %
and a daily XP goal + streak power the gamification. Deriving stages, reading
progress, and awarding XP all work with NO live key; only the Coach feedback on
challenge/draft turns calls the AI (with an offline mock fallback here).
"""
from __future__ import annotations

import json
from datetime import date

from ..core.config import settings
from ..db import repository as repo
from ..integrations.gemini_service import GeminiService, NoApiKey, Overloaded
from ..web.framework import HttpError
from . import ai_mock
from .preferences_service import user_profile_for_ai
from .tutor_service import get_lesson_context


def _xp() -> dict:
    return {
        "intro": settings.XP_INTRO, "video": settings.XP_VIDEO, "reading": settings.XP_READING,
        "challenge": settings.XP_CHALLENGE, "draft": settings.XP_DRAFT, "complete": settings.XP_COMPLETE,
    }


def _today() -> str:
    return date.today().isoformat()


_COACH_RULES = (
    'You are "Coach", a warm, encouraging bite-size tutor inside learning++. '
    'HARD RULE: never write the student\'s answer/solution/essay for them, not even "as an example" — '
    "if they ask, warmly refuse and give one tiny step they can take themselves. "
    "Keep it SHORT (2-4 sentences), lively, one idea at a time, sparing emoji."
)


# --- Stage derivation -------------------------------------------------------
def build_stages(lesson_id: int) -> tuple[dict, list[dict]]:
    lesson, _ = get_lesson_context(lesson_id)
    xp = _xp()
    blocks = [
        {"id": b["id"], "seq": b["seq"], "type": b["type"], "payload": json.loads(b["payload_json"])}
        for b in repo.list_lesson_blocks(lesson_id)
    ]
    videos = [b for b in blocks if b["type"] == "video"]
    readings = [b for b in blocks if b["type"] == "excerpt"]
    challenges = [b for b in blocks if b["type"] in ("scaffold_q", "flashcards")]
    drafts = [b for b in blocks if b["type"] == "draft"]

    stages: list[dict] = []
    stages.append({
        "key": "intro", "type": "intro", "title": f"Let's start: {lesson['title']}",
        "xp": xp["intro"],
        "body": "You'll watch, read, try a quick challenge, then write a piece of the real deliverable. Small steps — let's go.",
    })
    for b in videos:
        stages.append({"key": f"video:{b['id']}", "type": "video", "title": "Watch",
                       "xp": xp["video"], "blockId": b["id"], "payload": b["payload"]})
    for b in readings:
        stages.append({"key": f"reading:{b['id']}", "type": "reading", "title": "Read",
                       "xp": xp["reading"], "blockId": b["id"], "payload": b["payload"]})
    for b in challenges:
        if b["type"] == "flashcards":
            cards = b["payload"].get("cards") or []
            for i, card in enumerate(cards):
                stages.append({
                    "key": f"flashcard:{b['id']}:{i}", "type": "challenge",
                    "challengeKind": "flashcard", "title": "Challenge", "xp": xp["challenge"],
                    "blockId": b["id"], "prompt": card.get("front"), "answer": card.get("back"),
                    "allowReveal": True,
                })
        else:
            stages.append({
                "key": f"challenge:{b['id']}", "type": "challenge", "challengeKind": "scaffold",
                "title": "Challenge", "xp": xp["challenge"], "blockId": b["id"],
                "prompt": b["payload"].get("prompt"), "hint": b["payload"].get("hint") or None,
                "savesToAnswer": True, "allowReveal": False,
            })
    for b in drafts:
        stages.append({
            "key": f"draft:{b['id']}", "type": "draft", "title": "Draft the deliverable",
            "xp": xp["draft"], "blockId": b["id"], "prompt": b["payload"].get("instruction"),
            "rubricHint": b["payload"].get("rubricHint") or None, "savesToAnswer": True,
            "allowReveal": False,
        })
    stages.append({"key": "complete", "type": "complete", "title": "Complete!", "xp": xp["complete"]})
    return lesson, stages


# --- XP + progress ----------------------------------------------------------
def _ensure_user_xp(user_id: int | None) -> dict:
    if user_id is None:
        return {"user_id": None, "total_xp": 0, "daily_goal": settings.DAILY_XP_GOAL}
    return repo.ensure_user_xp(user_id, settings.DAILY_XP_GOAL)


def _award_stage(user_id: int | None, lesson_id: int, stage_key: str, xp: int) -> dict:
    if repo.get_xp_event(user_id, lesson_id, stage_key):
        return {"awarded": False, "xp": 0}
    repo.insert_xp_event(user_id, lesson_id, stage_key, xp, _today())
    if user_id is not None:
        _ensure_user_xp(user_id)
        repo.add_user_xp(user_id, xp)
    return {"awarded": True, "xp": xp}


def get_gamification_state(user_id: int | None) -> dict:
    xp_row = _ensure_user_xp(user_id)
    today_xp = repo.xp_earned_on(user_id, _today())
    streak_row = repo.get_lesson_streak(_today())
    daily_goal = xp_row["daily_goal"] if xp_row.get("daily_goal") is not None else settings.DAILY_XP_GOAL
    return {
        "totalXp": xp_row.get("total_xp", 0),
        "dailyGoal": daily_goal,
        "dailyXp": today_xp,
        "dailyGoalPct": min(100, round((today_xp / daily_goal) * 100)) if daily_goal > 0 else 0,
        "dailyGoalMet": today_xp >= daily_goal,
        "todayStreak": streak_row["completed_count"] if streak_row else 0,
    }


def get_flow(lesson_id: int, user_id: int | None) -> dict:
    lesson, stages = build_stages(lesson_id)
    assignment = repo.get_assignment(lesson["assignment_id"])
    done = repo.completed_stage_keys(user_id, lesson_id)

    work_stages = [s for s in stages if s["type"] != "complete"]
    done_work = sum(1 for s in work_stages if s["key"] in done)
    progress_pct = round((done_work / len(work_stages)) * 100) if work_stages else 0

    public_stages = []
    for s in stages:
        is_done = s["key"] in done
        out = {"key": s["key"], "type": s["type"], "title": s["title"], "xp": s["xp"], "done": is_done}
        if "blockId" in s:
            out["blockId"] = s["blockId"]
        for k in ("body", "payload", "prompt", "hint", "rubricHint", "challengeKind"):
            if s.get(k):
                out[k] = s[k]
        if s.get("allowReveal"):
            out["allowReveal"] = True
        if s.get("savesToAnswer"):
            out["savesToAnswer"] = True
        if s.get("challengeKind") == "flashcard" and is_done:
            out["answer"] = s.get("answer")
        if "blockId" in s and s["type"] in ("challenge", "draft"):
            ans = repo.get_answer_for_block(s["blockId"])
            if ans and ans["content_text"]:
                out["savedAnswer"] = ans["content_text"]
        public_stages.append(out)

    return {
        "lessonId": lesson["id"], "lessonTitle": lesson["title"], "lessonStatus": lesson["status"],
        "assignment": {"id": assignment["id"], "title": assignment["title"]} if assignment else None,
        "stages": public_stages,
        "progress": {
            "stagesTotal": len(work_stages), "stagesDone": done_work,
            "progressPct": progress_pct, "lessonComplete": lesson["status"] == "done",
        },
        "gamification": get_gamification_state(user_id),
    }


def _find_stage(lesson_id: int, stage_key: str) -> dict:
    _, stages = build_stages(lesson_id)
    for s in stages:
        if s["key"] == stage_key:
            return s
    raise HttpError(404, f'stage "{stage_key}" not found in lesson {lesson_id}')


def advance_stage(lesson_id: int, user_id: int | None, stage_key: str) -> dict:
    stage = _find_stage(lesson_id, stage_key)
    if stage["type"] not in ("intro", "video", "reading"):
        raise HttpError(400, f'stage "{stage_key}" is a {stage["type"]} stage — use the challenge/draft/complete endpoint')
    res = _award_stage(user_id, lesson_id, stage["key"], stage["xp"])
    return {"ok": True, "stageKey": stage["key"], "xpAwarded": res["xp"] if res["awarded"] else 0,
            "alreadyDone": not res["awarded"], "gamification": get_gamification_state(user_id)}


def _style_line(styles: list[str], notes: str) -> str:
    bits = []
    if styles:
        bits.append(f"They lean {' + '.join(styles)} — adapt examples/tone to that.")
    if notes:
        bits.append(f'They told us: "{notes}" — honor it.')
    return " ".join(bits)


def _coach_feedback(system: str, prompt: str) -> tuple[str, str]:
    svc = GeminiService()
    if svc.use_mock:
        return "", "mock"
    try:  # pragma: no cover - network path
        res = svc.generate_text(prompt=prompt, system=system,
                                temperature=settings.TUTOR_TEMPERATURE, history=[])
        return res["text"], res["model_used"]
    except (NoApiKey, Overloaded):  # pragma: no cover
        return "", "mock"


# --- flashcard correctness (lenient, ported) --------------------------------
def _normalize(s) -> str:
    out = []
    for ch in str(s or "").lower():
        out.append(ch if ch.isalnum() or ch.isspace() else " ")
    return " ".join("".join(out).split())


def _looks_correct(answer: str, known: str) -> bool:
    a, k = _normalize(answer), _normalize(known)
    if not a or not k:
        return False
    if a in k or k in a:
        return True
    k_tokens = list({w for w in k.split(" ") if len(w) > 2})
    if not k_tokens:
        return False
    a_set = set(a.split(" "))
    hit = sum(1 for t in k_tokens if t in a_set)
    return (hit / len(k_tokens)) >= 0.6


def submit_challenge(lesson_id: int, user_id: int | None, stage_key: str, raw_answer) -> dict:
    stage = _find_stage(lesson_id, stage_key)
    if stage["type"] != "challenge":
        raise HttpError(400, f'stage "{stage_key}" is not a challenge')
    answer = str(raw_answer or "").strip()
    if not answer:
        raise HttpError(400, "answer is required")

    lesson, assignment = get_lesson_context(lesson_id)
    prof = user_profile_for_ai(user_id)

    correct = None
    xp_result = {"awarded": False, "xp": 0}
    revealed = None

    if stage["challengeKind"] == "flashcard":
        correct = _looks_correct(answer, stage.get("answer") or "")
        if correct:
            xp_result = _award_stage(user_id, lesson_id, stage["key"], stage["xp"])
        if stage.get("allowReveal"):
            revealed = stage.get("answer")
    else:
        # scaffold_q: save the student's own words (compile reads this) + award.
        repo.save_answer_for_block(stage["blockId"], lesson["assignment_id"], answer)
        xp_result = _award_stage(user_id, lesson_id, stage["key"], stage["xp"])

    system = f"{_COACH_RULES} {_style_line(prof['learningStyles'], prof['learningNotes'])}".strip()
    prompt = _challenge_feedback_prompt(assignment, lesson, stage, answer, correct)
    feedback, model_used = _coach_feedback(system, prompt)
    if not feedback:
        feedback = ai_mock.mock_challenge_feedback(stage["challengeKind"], correct)

    return {
        "ok": True, "stageKey": stage["key"], "challengeKind": stage["challengeKind"],
        "correct": correct, "feedback": feedback, "revealed": revealed,
        "xpAwarded": xp_result["xp"] if xp_result["awarded"] else 0,
        "alreadyDone": (not xp_result["awarded"]) and (correct is True or stage["challengeKind"] != "flashcard"),
        "savedToAnswer": stage["challengeKind"] != "flashcard",
        "modelUsed": model_used, "gamification": get_gamification_state(user_id),
    }


def submit_draft(lesson_id: int, user_id: int | None, stage_key: str, raw_content) -> dict:
    stage = _find_stage(lesson_id, stage_key)
    if stage["type"] != "draft":
        raise HttpError(400, f'stage "{stage_key}" is not a draft')
    content = str(raw_content or "").strip()
    if not content:
        raise HttpError(400, "draft content is required")

    lesson, assignment = get_lesson_context(lesson_id)
    prof = user_profile_for_ai(user_id)

    # Save + award BEFORE the AI call so no work is lost on no-key/overload.
    repo.save_answer_for_block(stage["blockId"], lesson["assignment_id"], content)
    xp_result = _award_stage(user_id, lesson_id, stage["key"], stage["xp"])

    system = f"{_COACH_RULES} {_style_line(prof['learningStyles'], prof['learningNotes'])}".strip()
    prompt = (
        "The student just drafted their deliverable for this lesson. Give warm, specific feedback: "
        "name ONE thing they did well, then ONE concrete improvement they can make themselves. "
        "Do NOT rewrite it or supply the corrected version — nudge only.\n\n"
        f"Assignment: {assignment.get('title', 'unknown')}\n"
        f"Task: {stage.get('prompt')}\n"
        + (f"Rubric hint: {stage.get('rubricHint')}\n" if stage.get('rubricHint') else "")
        + f'\nStudent\'s draft:\n"""{content}"""'
    )
    feedback, model_used = _coach_feedback(system, prompt)
    if not feedback:
        feedback = ai_mock.mock_draft_feedback()

    return {
        "ok": True, "stageKey": stage["key"], "feedback": feedback,
        "xpAwarded": xp_result["xp"] if xp_result["awarded"] else 0,
        "alreadyDone": not xp_result["awarded"], "savedToAnswer": True,
        "modelUsed": model_used, "gamification": get_gamification_state(user_id),
    }


def complete_flow(lesson_id: int, user_id: int | None) -> dict:
    lesson, _ = get_lesson_context(lesson_id)
    was_done = lesson["status"] == "done"
    repo.set_lesson_status(lesson_id, "done")
    if not was_done:
        repo.bump_lesson_streak(_today())
    bonus = _award_stage(user_id, lesson_id, "complete", _xp()["complete"])
    return {
        "ok": True, "lessonId": lesson_id, "lessonComplete": True,
        "firstCompletion": not was_done,
        "completionBonus": bonus["xp"] if bonus["awarded"] else 0,
        "gamification": get_gamification_state(user_id),
    }


def _challenge_feedback_prompt(assignment: dict, lesson: dict, stage: dict, answer: str, correct) -> str:
    if stage["challengeKind"] == "flashcard":
        base = (
            f"Quick recall challenge in the lesson \"{lesson['title']}\".\n"
            f"Question: {stage.get('prompt')}\n"
            f"Expected idea: {stage.get('answer')}\n"
            f'Student answered: "{answer}"\n'
            f"They were judged {'CORRECT' if correct else 'NOT QUITE'}. "
        )
        base += ("Celebrate specifically what they nailed in one upbeat line."
                 if correct else
                 'Gently say "not quite" and give ONE small nudge toward the idea — do NOT state the full answer.')
        return base
    return (
        f"Open challenge in the lesson \"{lesson['title']}\" (assignment: {assignment.get('title', 'unknown')}).\n"
        f"Prompt: {stage.get('prompt')}\n"
        + (f"Hint available: {stage.get('hint')}\n" if stage.get('hint') else "")
        + f'Student answered in their own words: "{answer}"\n'
        "React to what they ACTUALLY wrote: if on track, celebrate the specific good part and push "
        "them one step further; if off, nudge with a hint or a simpler sub-question so they get there "
        "themselves. NEVER give them the answer outright."
    )
