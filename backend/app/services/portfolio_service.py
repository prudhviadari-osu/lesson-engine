"""Portfolio — the product's point of uniqueness (ported from portfolio.js).

Two halves (mirrors the product spec):
  1. Portfolio GUIDE   — AI-recommended projects built from the skills the
                         student has gained, each with a "Get Help" that turns
                         the project into a real, playable gamified lesson flow.
  2. PERSONAL portfolio — a resume-friendly view of their completed coursework
                         + accepted projects + accumulated skills + stats.

Design choices (matching the rest of the unified Python app):
  - All AI goes through GeminiService.generate_json (structured + CACHED by
    input hash). Skill extraction + project recommendation pass a stable
    cache-key so re-opening the Portfolio tab is instant/offline.
  - OFFLINE MOCK: with no GEMINI_API_KEY (settings.USE_MOCK_INTEGRATIONS) the
    AI calls fall back to deterministic mocks (ai_mock), so the feature works
    fully offline exactly like decompose/tutor.
  - Skills PERSIST (user_skill) because the loop "finish work -> gain skills ->
    recommend more" accumulates over time. UNIQUE(user_id, skill) makes
    re-extraction idempotent.
  - Recommendations are derived ON DEMAND (+ cached); only projects the student
    accepts are persisted (portfolio_project).
  - Reads lean on the SAME completed-work basis compile uses: a skill is only
    credited from work the student actually finished (honesty-by-design).
  - "Get Help" materializes the project as a self-assigned assignment and runs
    it through the EXISTING decompose + resolve + flow pipeline — no new lesson
    code. The flow is reachable at the usual course-scoped lesson endpoints,
    so the student's own private "Portfolio projects" course is used.

Canvas ingest + live job-board search are deliberately OUT of scope here — this
runs entirely on data already in the DB.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from ..db import repository as repo
from ..integrations.gemini_service import GeminiService, NoApiKey, Overloaded
from ..web.framework import HttpError
from . import ai_mock
from .flow_service import get_gamification_state
from .preferences_service import user_profile_for_ai
from .decompose_service import decompose_assignment
from .resolve_service import resolve_resources

logger = logging.getLogger("learnpp.portfolio")

PORTFOLIO_COURSE_CODE = "PORTFOLIO"
PORTFOLIO_COURSE_TITLE = "Portfolio projects"
VALID_STATUSES = ("recommended", "in_progress", "done")


# --- Completed-work reads (honesty-by-design; mirrors compile) --------------
def _completed_work(user_id: int) -> list[dict]:
    work = repo.list_completed_work_for_user(user_id)
    for a in work:
        a["completedLessons"] = repo.list_completed_lesson_titles(a["id"])
    return work


# --- Skills (persisted) -----------------------------------------------------
def get_skills(user_id: int) -> list[dict]:
    rows = repo.list_user_skills(user_id)
    return [
        {"skill": r["skill"], "source": r["source"],
         "evidence": r["evidence"], "createdAt": r["created_at"]}
        for r in rows
    ]


def _persist_skills(user_id: int, skills: list[dict], source: str) -> None:
    for s in skills:
        skill = str(s.get("skill") or "").strip()
        if not skill:
            continue
        repo.upsert_user_skill(user_id, skill, source, str(s.get("evidence") or "").strip())


def _skills_prompt(work: list[dict]) -> str:
    lines = []
    for a in work:
        lessons = a.get("completedLessons") or []
        lesson_str = f"\n  Completed lessons: {'; '.join(lessons)}" if lessons else ""
        course = a.get("course_code") or a.get("course_title") or "coursework"
        lines.append(
            f"- [{course}] {a.get('title')}\n  "
            f"{a.get('description') or '(no description)'}{lesson_str}"
        )
    work_text = "\n".join(lines)
    return (
        "You are a career advisor reviewing a student's COMPLETED coursework to build a resume.\n"
        "From ONLY the work below, name the concrete, resume-worthy skills it genuinely "
        "demonstrates (languages, tools, techniques, concepts). Be specific and honest — do NOT "
        "invent skills the work doesn't show. Prefer 5-12 well-grounded skills.\n"
        'Return STRICT JSON: {"skills":[{"skill":str,"evidence":str}]} where evidence is one '
        "short phrase naming which assignment/concept demonstrated it.\n\n"
        f"COMPLETED WORK:\n{work_text}\n\nList the skills now."
    )


def extract_skills(user_id: int) -> dict:
    """Extract skills from completed coursework and persist them.

    Idempotent + cached (same completed work -> same cached result). Returns the
    current skills unchanged if there's no completed work yet. Uses the offline
    mock when no Gemini key is present.
    """
    user = repo.get_user(user_id)
    if user is None:
        raise HttpError(404, "user not found")

    work = _completed_work(user_id)
    if not work:
        return {
            "extracted": 0, "skills": get_skills(user_id),
            "note": "no completed work yet — finish a lesson first",
        }

    svc = GeminiService()
    if svc.use_mock:
        data = ai_mock.mock_portfolio_skills(work)
    else:  # pragma: no cover - network path
        try:
            res = svc.generate_json(
                prompt=_skills_prompt(work),
                cache_key_extra=f"portfolio-skills:{user_id}:{','.join(str(a['id']) for a in work)}",
            )
            data = res["data"]
        except (NoApiKey, Overloaded) as exc:
            logger.warning("skill extraction fell back to mock (%s)", exc)
            data = ai_mock.mock_portfolio_skills(work)
        except Exception as exc:
            logger.warning("skill extraction Gemini error (%s); using mock", exc)
            data = ai_mock.mock_portfolio_skills(work)

    skills = data.get("skills") if isinstance(data, dict) else None
    skills = skills if isinstance(skills, list) else []
    _persist_skills(user_id, skills, "coursework")
    return {"extracted": len(skills), "skills": get_skills(user_id)}


# --- Portfolio Guide (recommended projects) ---------------------------------
def _projects_prompt(skill_names: list[str], count: int) -> str:
    skill_list = ", ".join(skill_names)
    return (
        f"A student possesses the following skills:\n{skill_list}\n\n"
        f"Generate {count} portfolio-worthy projects that build on these skills. "
        "Favor practical projects that strengthen a software-engineering resume. For each "
        "project include: name, difficulty (Beginner|Intermediate|Advanced), a 1-2 sentence "
        "description, skillsReinforced (from their existing skills), newSkills (they'd learn), "
        "and a rough time estimate.\n"
        'Return STRICT JSON: {"projects":[{"name":str,"difficulty":str,"description":str,'
        '"skillsReinforced":[str],"newSkills":[str],"time":str}]}. Produce the projects now.'
    )


def recommend_projects(user_id: int, count: int = 5) -> dict:
    """Recommend portfolio projects from the student's current skills.

    Extracts skills first if the student has none yet (so the Guide works on
    first open). Cached by the skill set + count. Uses the offline mock with no
    Gemini key.
    """
    user = repo.get_user(user_id)
    if user is None:
        raise HttpError(404, "user not found")

    skills = get_skills(user_id)
    if not skills:
        extract_skills(user_id)
        skills = get_skills(user_id)

    if not skills:
        return {
            "projects": [], "skills": [],
            "note": "no skills yet — complete some coursework first",
        }

    skill_names = [s["skill"] for s in skills]
    svc = GeminiService()
    cached = False
    if svc.use_mock:
        data = ai_mock.mock_portfolio_projects(skill_names, count)
    else:  # pragma: no cover - network path
        try:
            key = ":".join(sorted(skill_names))
            res = svc.generate_json(
                prompt=_projects_prompt(skill_names, count),
                cache_key_extra=f"portfolio-projects:{user_id}:{key}:{count}",
            )
            data = res["data"]
            cached = res["cached"]
        except (NoApiKey, Overloaded) as exc:
            logger.warning("project recommendation fell back to mock (%s)", exc)
            data = ai_mock.mock_portfolio_projects(skill_names, count)
        except Exception as exc:
            logger.warning("project recommendation Gemini error (%s); using mock", exc)
            data = ai_mock.mock_portfolio_projects(skill_names, count)

    projects = data.get("projects") if isinstance(data, dict) else None
    projects = projects if isinstance(projects, list) else []
    return {"projects": projects, "cached": cached, "skills": skills}


# --- Accepted projects (persisted) ------------------------------------------
def save_project(user_id: int, project: dict | None) -> dict:
    user = repo.get_user(user_id)
    if user is None:
        raise HttpError(404, "user not found")
    if not isinstance(project, dict):
        raise HttpError(400, "project is required")
    name = str(project.get("name") or "").strip()
    if not name:
        raise HttpError(400, "project.name is required")

    pid = repo.create_portfolio_project(
        user_id, name, project.get("difficulty"), json.dumps(project), "recommended"
    )
    return {"id": pid, "name": name, "status": "recommended"}


def set_project_status(user_id: int, project_id: int, status) -> dict:
    status = str(status or "").strip()
    if status not in VALID_STATUSES:
        raise HttpError(400, f"status must be one of {', '.join(VALID_STATUSES)}")
    changed = repo.set_portfolio_project_status(user_id, project_id, status)
    if changed == 0:
        raise HttpError(404, "project not found")
    return {"id": int(project_id), "status": status}


def _saved_projects(user_id: int) -> list[dict]:
    out = []
    for r in repo.list_portfolio_projects(user_id):
        out.append({
            "id": r["id"], "name": r["name"], "difficulty": r["difficulty"],
            "status": r["status"], "assignmentId": r["assignment_id"],
            "spec": _safe_json(r["spec_json"]), "createdAt": r["created_at"],
        })
    return out


# --- "Get Help": turn a project into a real, playable gamified lesson flow ---
def _ensure_portfolio_course(user_id: int) -> dict:
    """Find (or lazily create) this student's private "Portfolio projects" course.

    The staged flow is reached through the normal course-scoped endpoints, which
    require enrollment, so the student is enrolled in their own portfolio course.
    """
    course = repo.get_portfolio_course_for_user(user_id)
    if course is None:
        cid = repo.create_course(
            code=PORTFOLIO_COURSE_CODE, title=PORTFOLIO_COURSE_TITLE,
            section=f"u{user_id}", term="AU25",
        )
        repo.create_enrollment(user_id, cid, "student")
        course = repo.get_course(cid)
    elif repo.get_enrollment(user_id, course["id"]) is None:
        repo.create_enrollment(user_id, course["id"], "student")
    return course


def _project_to_description(project: dict) -> str:
    reinforced = project.get("skillsReinforced") if isinstance(project.get("skillsReinforced"), list) else []
    fresh = project.get("newSkills") if isinstance(project.get("newSkills"), list) else []
    using = list(dict.fromkeys([*reinforced, *fresh]))
    parts = [f'Build a portfolio project: "{project.get("name")}".']
    if project.get("description"):
        parts.append(project["description"])
    if project.get("difficulty"):
        parts.append(f"Target difficulty: {project['difficulty']}.")
    if using:
        parts.append(f"Use and strengthen these skills: {', '.join(using)}.")
    if fresh:
        parts.append(f"Along the way the student should newly learn: {', '.join(fresh)}.")
    parts.append(
        "Teach the student to build this themselves in small milestones — each lesson should "
        "cover one buildable step, with the student writing/producing the actual work (never "
        "hand them finished code)."
    )
    return " ".join(parts)


def get_project_help(user_id: int, project: dict | None) -> dict:
    """Materialize a chosen project as a self-assigned assignment and run it
    through the SAME decompose -> resolve pipeline, producing a real gamified
    staged lesson flow (reachable at the usual lesson endpoints).

    Idempotent per saved project: if help was already requested (the row has an
    assignment_id), reuse that assignment. If the project isn't saved yet, save
    it first so the lesson flow links back to a persisted card.
    """
    user = repo.get_user(user_id)
    if user is None:
        raise HttpError(404, "user not found")
    if not isinstance(project, dict):
        raise HttpError(400, "project is required")
    name = str(project.get("name") or "").strip()
    if not name:
        raise HttpError(400, "project.name is required")

    # Reuse an existing saved row (by id, then by name) to avoid duplicate cards.
    row = None
    if project.get("id"):
        row = repo.get_portfolio_project(int(project["id"]), user_id)
    if row is None:
        row = repo.get_portfolio_project_by_name(user_id, name)
    if row is None:
        saved = save_project(user_id, project)
        row = repo.get_portfolio_project(saved["id"], user_id)

    # Already has a lesson flow? Reuse it (idempotent — no duplicate assignment).
    if row.get("assignment_id"):
        existing = repo.get_assignment(row["assignment_id"])
        if existing:
            return {
                "projectId": row["id"], "assignmentId": row["assignment_id"],
                "reused": True, "lessons": repo.list_assignment_lessons_brief(row["assignment_id"]),
            }

    # Create the self-assigned assignment under the private portfolio course.
    course = _ensure_portfolio_course(user_id)
    spec = {**_safe_json(row.get("spec_json")), **project, "name": name}
    description = _project_to_description(spec)
    assignment_id = repo.create_assignment(
        course_id=course["id"], title=name, description=description,
        kind="project", due_at=_default_due_at(),
    )
    assignment = repo.get_assignment(assignment_id)

    # Run the SAME pipeline as any assignment: decompose (honors the learner
    # profile), then resolve video/reading resources (keyless-safe, best-effort).
    prof = user_profile_for_ai(user_id)
    decompose_assignment(assignment, user_id, prof["learningStyles"], prof["learningNotes"])
    try:
        resolve_resources(assignment_id)
    except Exception as exc:  # pragma: no cover - resources are non-critical
        logger.warning("resource resolution failed for portfolio assignment %s (%s)", assignment_id, exc)

    repo.link_portfolio_project_assignment(row["id"], assignment_id)
    return {
        "projectId": row["id"], "assignmentId": assignment_id, "courseId": course["id"],
        "reused": False, "lessons": repo.list_assignment_lessons_brief(assignment_id),
    }


# --- Personal Portfolio (resume-friendly view) ------------------------------
def get_personal_portfolio(user_id: int) -> dict:
    """Resume-friendly snapshot assembled from the student's completed
    coursework, accumulated skills, saved projects, and gamification stats.
    Pure DB reads — no live API call, always safe to serve.
    """
    user = repo.get_user(user_id)
    if user is None:
        raise HttpError(404, "user not found")

    completed_work = _completed_work(user_id)
    return {
        "user": {"id": user["id"], "displayName": user["full_name"]},
        "skills": get_skills(user_id),
        "coursesCompleted": repo.list_completed_courses_for_user(user_id),
        "completedWork": [
            {
                "assignmentId": a["id"], "title": a["title"],
                "course": a.get("course_code") or a.get("course_title"),
                "completedLessons": a["completedLessons"],
            }
            for a in completed_work
        ],
        "projects": _saved_projects(user_id),
        "stats": get_gamification_state(user_id),
    }


# --- helpers ----------------------------------------------------------------
def _default_due_at() -> str:
    """Self-assigned portfolio projects have no hard deadline; give a soft
    2-week horizon so the planner + due-date-driven UI still behave sensibly."""
    return (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()


def _safe_json(text) -> dict:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}
