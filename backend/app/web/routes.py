"""All HTTP routes for Learn++."""
from __future__ import annotations

import json
import re

from ..core.security import create_access_token, hash_password, verify_password
from ..db import repository as repo
from ..integrations import OSUAuth, OSUClassSearch
from ..services import compile_service, flow_service, planner_service, tutor_service
from ..services.decompose_service import decompose_assignment
from ..services.lesson_service import (
    autogenerate_due_soon,
    generate_lesson_for_assignment,
)
from ..services.onboarding_service import sync_user_from_canvas
from ..services.preferences_service import (
    get_preferences,
    set_preferences,
    user_profile_for_ai,
)
from ..services.resolve_service import resolve_resources
from .access import require_course_access, require_course_instructor
from .framework import HttpError, Request, Router

router = Router()

_PUBLIC_USER_FIELDS = (
    "id", "email", "username", "full_name", "role", "org_verified", "bio",
    "avatar_url", "github_url", "linkedin_url", "major", "grad_year", "company",
)
_BLOCKED_SOCIAL = ("instagram.com", "tiktok.com", "youtube.com", "youtu.be",
                   "facebook.com", "twitter.com", "x.com")


def _public_user(user: dict) -> dict:
    return {k: user.get(k) for k in _PUBLIC_USER_FIELDS}


def _require(body: dict, *fields: str) -> None:
    missing = [f for f in fields if not body.get(f)]
    if missing:
        raise HttpError(400, f"Missing required field(s): {', '.join(missing)}")


# =============================== meta ======================================
@router.get("/api/health")
def health(req: Request):
    from ..core.config import settings
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "mock_integrations": settings.USE_MOCK_INTEGRATIONS,
        "database": "sqlite",
    }


# =============================== auth ======================================
@router.post("/api/auth/signup")
def signup(req: Request):
    b = req.body
    _require(b, "email", "username", "full_name", "password")
    role = b.get("role", "student")
    if role not in {"student", "professor", "admin", "recruiter"}:
        raise HttpError(400, "Invalid role")
    if len(b["password"]) < 6:
        raise HttpError(400, "Password must be at least 6 characters")
    if repo.get_user_by_email(b["email"]):
        raise HttpError(409, "Email already registered")
    if repo.get_user_by_username(b["username"]):
        raise HttpError(409, "Username already taken")

    osu = OSUAuth()
    if role in {"student", "professor"}:
        if not osu.verify_exists(b.get("osu_name_dot_number")):
            raise HttpError(400, "OSU identity could not be verified. Use a valid name.# (e.g. buckeye.1).")

    company = b.get("company")
    if role == "recruiter":
        reg = repo.get_registered_recruiter(b["email"])
        if reg is None:
            raise HttpError(403, "This email is not on the authorized recruiter registry.")
        company = company or reg["company"]

    uid = repo.create_user(
        email=b["email"], username=b["username"], full_name=b["full_name"],
        hashed_password=hash_password(b["password"]), role=role,
        org_verified=1 if role in {"student", "professor", "recruiter"} else 0,
        osu_name_dot_number=b.get("osu_name_dot_number"), company=company,
    )
    user = repo.get_user(uid)

    if role == "student":
        sync_user_from_canvas(user)
        autogenerate_due_soon()

    token = create_access_token(str(uid), {"role": role})
    return {"status": 201, "access_token": token, "token_type": "bearer",
            "user": _public_user(user)}


def _auth_check(b: dict) -> dict:
    _require(b, "email", "password", "role")
    user = repo.get_user_by_email(b["email"])
    if user is None or not verify_password(b["password"], user["hashed_password"]):
        raise HttpError(401, "Invalid credentials")
    if user["role"] != b["role"]:
        raise HttpError(403, f"This account is registered as '{user['role']}', not '{b['role']}'.")
    return user


@router.post("/api/auth/login/verify")
def login_verify(req: Request):
    user = _auth_check(req.body)
    if user["role"] in {"student", "professor"}:
        challenge = OSUAuth().start_two_factor(user.get("osu_name_dot_number") or "")
        return {"requires_2fa": True, **challenge}
    return {"requires_2fa": False}


@router.post("/api/auth/login")
def login(req: Request):
    user = _auth_check(req.body)
    token = create_access_token(str(user["id"]), {"role": user["role"]})
    return {"access_token": token, "token_type": "bearer", "user": _public_user(user)}


@router.post("/api/auth/login/2fa")
def login_2fa(req: Request):
    b = req.body
    _require(b, "email", "code")
    user = repo.get_user_by_email(b["email"])
    if user is None:
        raise HttpError(401, "Unknown account")
    if not OSUAuth().verify_two_factor(user.get("osu_name_dot_number") or "", b["code"]):
        raise HttpError(401, "Invalid two-factor code")
    token = create_access_token(str(user["id"]), {"role": user["role"]})
    return {"access_token": token, "token_type": "bearer", "user": _public_user(user)}


# =============================== users =====================================
@router.get("/api/users/me")
def me(req: Request):
    return _public_user(req.current_user())


@router.put("/api/users/me")
def update_me(req: Request):
    user = req.current_user()
    b = req.body
    gh, li = b.get("github_url"), b.get("linkedin_url")
    for url, field in ((gh, "github_url"), (li, "linkedin_url")):
        if url and any(h in url.lower() for h in _BLOCKED_SOCIAL):
            raise HttpError(400, f"Social media links are not allowed in {field}.")
    if gh and "github.com" not in gh.lower():
        raise HttpError(400, "github_url must be a github.com link.")
    if li and "linkedin.com" not in li.lower():
        raise HttpError(400, "linkedin_url must be a linkedin.com link.")

    allowed = {"full_name", "bio", "avatar_url", "github_url", "linkedin_url", "major", "grad_year"}
    fields = {k: v for k, v in b.items() if k in allowed}
    repo.update_user(user["id"], fields)
    return _public_user(repo.get_user(user["id"]))


@router.get("/api/users/{user_id}")
def public_profile(req: Request):
    req.current_user()
    target = repo.get_user(int(req.params["user_id"]))
    if target is None:
        raise HttpError(404, "User not found")
    return _public_user(target)


# =============================== courses ===================================
@router.get("/api/courses")
def my_courses(req: Request):
    user = req.current_user()
    if user["role"] == "recruiter":
        return []
    if user["role"] == "admin":
        return repo.list_all_courses()
    return repo.list_user_courses(user["id"])


@router.get("/api/courses/{course_id}/members")
def course_members(req: Request):
    cid = int(req.params["course_id"])
    require_course_access(req, cid)
    return repo.list_course_members(cid)


@router.get("/api/courses/{course_id}/assignments")
def course_assignments(req: Request):
    cid = int(req.params["course_id"])
    require_course_access(req, cid)
    items = repo.list_course_assignments(cid)
    for a in items:
        a["lessons"] = repo.list_lessons_for_assignment(a["id"])
        a["has_lessons"] = len(a["lessons"]) > 0
    return items


# --------------------- interactive lesson engine --------------------------
def _access_assignment(req: Request, course_id: int, assignment_id: int) -> tuple[dict, dict]:
    """Verify the acting user may access an assignment in a course."""
    user = require_course_access(req, course_id)
    assignment = repo.get_assignment(assignment_id)
    if assignment is None or assignment["course_id"] != course_id:
        raise HttpError(404, "Assignment not found in this course")
    return user, assignment


def _lesson_course_id(lesson_id: int) -> tuple[dict, int]:
    lesson = repo.get_lesson(lesson_id)
    if lesson is None:
        raise HttpError(404, "lesson not found")
    assignment = repo.get_assignment(lesson["assignment_id"])
    if assignment is None:
        raise HttpError(404, "assignment not found")
    return lesson, assignment["course_id"]


def _access_lesson(req: Request, lesson_id: int) -> dict:
    """Verify the acting user may access a lesson (via its course)."""
    _, cid = _lesson_course_id(lesson_id)
    return require_course_access(req, cid)


@router.get("/api/courses/{course_id}/assignments/{assignment_id}/lessons")
def assignment_lessons(req: Request):
    cid = int(req.params["course_id"])
    aid = int(req.params["assignment_id"])
    user, assignment = _access_assignment(req, cid, aid)
    if not repo.assignment_has_lessons(aid):
        generate_lesson_for_assignment(assignment, user_id=user["id"])
    lessons = repo.list_lessons_for_assignment(aid)
    for l in lessons:
        l["blocks"] = [
            {"id": b["id"], "seq": b["seq"], "type": b["type"],
             "payload": json.loads(b["payload_json"])}
            for b in repo.list_lesson_blocks(l["id"])
        ]
    return {"assignmentId": aid, "title": assignment["title"], "lessons": lessons}


@router.post("/api/courses/{course_id}/assignments/{assignment_id}/decompose")
def decompose_route(req: Request):
    cid = int(req.params["course_id"])
    aid = int(req.params["assignment_id"])
    user, assignment = _access_assignment(req, cid, aid)
    prof = user_profile_for_ai(user["id"])
    result = decompose_assignment(assignment, user["id"], prof["learningStyles"], prof["learningNotes"])
    resolve_resources(aid)
    result["appliedProfile"] = prof
    return result


# ---- staged flow (the main gamified lesson experience) ----
@router.get("/api/lessons/{lesson_id}/flow")
def lesson_flow(req: Request):
    lid = int(req.params["lesson_id"])
    user = _access_lesson(req, lid)
    return flow_service.get_flow(lid, user["id"])


@router.post("/api/lessons/{lesson_id}/flow/advance")
def lesson_flow_advance(req: Request):
    lid = int(req.params["lesson_id"])
    user = _access_lesson(req, lid)
    _require(req.body, "stageKey")
    return flow_service.advance_stage(lid, user["id"], req.body["stageKey"])


@router.post("/api/lessons/{lesson_id}/flow/challenge")
def lesson_flow_challenge(req: Request):
    lid = int(req.params["lesson_id"])
    user = _access_lesson(req, lid)
    _require(req.body, "stageKey")
    return flow_service.submit_challenge(lid, user["id"], req.body["stageKey"], req.body.get("answer"))


@router.post("/api/lessons/{lesson_id}/flow/draft")
def lesson_flow_draft(req: Request):
    lid = int(req.params["lesson_id"])
    user = _access_lesson(req, lid)
    _require(req.body, "stageKey")
    return flow_service.submit_draft(lid, user["id"], req.body["stageKey"], req.body.get("content"))


@router.post("/api/lessons/{lesson_id}/flow/complete")
def lesson_flow_complete(req: Request):
    lid = int(req.params["lesson_id"])
    user = _access_lesson(req, lid)
    return flow_service.complete_flow(lid, user["id"])


# ---- interactive Coach tutor ----
@router.get("/api/lessons/{lesson_id}/tutor")
def tutor_history(req: Request):
    lid = int(req.params["lesson_id"])
    user = _access_lesson(req, lid)
    return {"lessonId": lid, "history": tutor_service.get_history(lid, user["id"])}


@router.post("/api/lessons/{lesson_id}/tutor/start")
def tutor_start(req: Request):
    lid = int(req.params["lesson_id"])
    user = _access_lesson(req, lid)
    reset = bool(req.body.get("reset")) if req.body else False
    return tutor_service.start_session(lid, user["id"], reset=reset)


@router.post("/api/lessons/{lesson_id}/tutor")
def tutor_message(req: Request):
    lid = int(req.params["lesson_id"])
    user = _access_lesson(req, lid)
    return tutor_service.send_message(lid, user["id"], (req.body or {}).get("message"))


# ---- compile + review/consent ----
@router.get("/api/courses/{course_id}/assignments/{assignment_id}/compile")
def compile_route(req: Request):
    cid = int(req.params["course_id"])
    aid = int(req.params["assignment_id"])
    user, _ = _access_assignment(req, cid, aid)
    return compile_service.compile_assignment(aid, user["id"])


@router.post("/api/courses/{course_id}/assignments/{assignment_id}/compile/consent")
def compile_consent(req: Request):
    cid = int(req.params["course_id"])
    aid = int(req.params["assignment_id"])
    user, _ = _access_assignment(req, cid, aid)
    b = req.body or {}
    if b.get("reviewed") is not True or b.get("consented") is not True:
        raise HttpError(400, "both reviewed:true and consented:true are required to mark ready")
    return compile_service.record_consent(aid, user["id"], True, True, b.get("contentHash"))


# ---- learning-style preferences ----
@router.get("/api/users/me/preferences")
def get_my_preferences(req: Request):
    user = req.current_user()
    return get_preferences(user["id"])


@router.put("/api/users/me/preferences")
def set_my_preferences(req: Request):
    user = req.current_user()
    b = req.body or {}
    return set_preferences(user["id"], b.get("learningStyles"), b.get("learningNotes"))


# ---- planner + reflow (student) ----
@router.get("/api/plan")
def plan_get(req: Request):
    user = req.require_roles("student", "admin")
    return planner_service.get_plan(user["id"])


@router.post("/api/plan/reflow")
def plan_reflow(req: Request):
    user = req.require_roles("student", "admin")
    return planner_service.generate_plan(user["id"])


@router.post("/api/plan/lessons/{lesson_id}/unschedule")
def plan_unschedule(req: Request):
    user = req.require_roles("student", "admin")  # noqa: F841
    lid = int(req.params["lesson_id"])
    ok = planner_service.unschedule_lesson(lid)
    return {"ok": ok, "action": "unscheduled"}


@router.post("/api/plan/lessons/{lesson_id}/reschedule")
def plan_reschedule(req: Request):
    user = req.require_roles("student", "admin")
    lid = int(req.params["lesson_id"])
    ok = planner_service.reschedule_lesson(user["id"], lid)
    if not ok:
        raise HttpError(404, "lesson not found for this user")
    return {"ok": ok, "action": "rescheduled"}


@router.post("/api/plan/clear")
def plan_clear(req: Request):
    user = req.require_roles("student", "admin")
    cleared = planner_service.clear_plan(user["id"])
    return {"ok": True, "cleared": cleared, "action": "plan_cleared"}


# =============================== forums ====================================
@router.get("/api/courses/{course_id}/forum/threads")
def list_threads(req: Request):
    cid = int(req.params["course_id"])
    user = require_course_access(req, cid)
    include_hidden = user["role"] in {"professor", "admin"}
    threads = repo.list_threads(cid)
    for t in threads:
        t["posts"] = repo.list_posts(t["id"], include_hidden)
    return threads


@router.post("/api/courses/{course_id}/forum/threads")
def create_thread(req: Request):
    cid = int(req.params["course_id"])
    user = require_course_access(req, cid)
    _require(req.body, "title")
    tid = repo.create_thread(cid, user["id"], req.body["title"], req.body.get("body", ""))
    t = repo.get_thread(tid)
    t["posts"] = []
    return {"status": 201, **t}


@router.post("/api/courses/{course_id}/forum/threads/{thread_id}/posts")
def reply(req: Request):
    cid = int(req.params["course_id"])
    tid = int(req.params["thread_id"])
    user = require_course_access(req, cid)
    _require(req.body, "body")
    thread = repo.get_thread(tid)
    if thread is None or thread["course_id"] != cid:
        raise HttpError(404, "Thread not found in this course")
    repo.create_post(tid, user["id"], req.body["body"])
    thread["posts"] = repo.list_posts(tid, user["role"] in {"professor", "admin"})
    return {"status": 201, **thread}


@router.post("/api/courses/{course_id}/forum/posts/{post_id}/moderate")
def moderate_post(req: Request):
    cid = int(req.params["course_id"])
    pid = int(req.params["post_id"])
    require_course_instructor(req, cid)
    post = repo.get_post(pid)
    if post is None:
        raise HttpError(404, "Post not found")
    thread = repo.get_thread(post["thread_id"])
    if thread is None or thread["course_id"] != cid:
        raise HttpError(404, "Post not found in this course")
    hide = req.body.get("hide", True) if req.body else (req.query.get("hide", "true") == "true")
    repo.set_post_hidden(pid, bool(hide))
    return {"post_id": pid, "hidden": bool(hide)}


# =============================== projects ==================================
@router.get("/api/projects/guided/{course_id}")
def guided_projects(req: Request):
    cid = int(req.params["course_id"])
    require_course_access(req, cid)
    return repo.list_guided_projects(cid)


@router.get("/api/projects/showcase")
def showcase_projects(req: Request):
    req.current_user()  # any authenticated role, including registered recruiters
    projects = repo.list_showcase_projects()
    for p in projects:
        p["comments"] = repo.list_project_comments(p["id"])
    return projects


@router.post("/api/projects/showcase")
def publish_showcase(req: Request):
    user = req.require_roles("student")
    _require(req.body, "title")
    pid = repo.create_project(
        project_type="showcase", owner_id=user["id"], title=req.body["title"],
        description=req.body.get("description", ""), repo_url=req.body.get("repo_url"),
        demo_url=req.body.get("demo_url"), tech_stack=req.body.get("tech_stack"),
        published=True,
    )
    p = repo.get_project(pid)
    p["comments"] = []
    return {"status": 201, **p}


@router.post("/api/projects/{project_id}/comments")
def comment(req: Request):
    pid = int(req.params["project_id"])
    user = req.current_user()
    _require(req.body, "body")
    project = repo.get_project(pid)
    if project is None:
        raise HttpError(404, "Project not found")
    if project["project_type"] == "guided":
        if user["role"] == "recruiter":
            raise HttpError(403, "Recruiters cannot access guided projects")
        if user["role"] != "admin" and repo.get_enrollment(user["id"], project["course_id"]) is None:
            raise HttpError(403, "Not enrolled in this course")
    if not user["org_verified"]:
        raise HttpError(403, "Only verified users may comment")
    repo.create_project_comment(pid, user["id"], req.body["body"])
    project["comments"] = repo.list_project_comments(pid)
    return {"status": 201, **project}


# ============================= announcements ===============================
@router.get("/api/announcements")
def list_announcements(req: Request):
    user = req.current_user()
    is_admin = user["role"] == "admin"
    course_ids = [c["id"] for c in repo.list_user_courses(user["id"])]
    return repo.list_announcements_for_user(course_ids, is_admin)


@router.post("/api/announcements")
def create_announcement(req: Request):
    user = req.require_roles("professor", "admin")
    _require(req.body, "title")
    course_id = req.body.get("course_id")
    if course_id is not None and user["role"] == "professor":
        if repo.get_enrollment(user["id"], int(course_id)) is None:
            raise HttpError(403, "You can only post to your own courses")
    aid = repo.create_announcement(
        course_id=course_id, author_id=user["id"], title=req.body["title"],
        body=req.body.get("body", ""), category=req.body.get("category", "event"),
        location=req.body.get("location"), event_at=req.body.get("event_at"),
    )
    return {"status": 201, "id": aid}


# =============================== advisor ===================================
@router.get("/api/advisor/recommendations")
def recommendations(req: Request):
    user = req.require_roles("student")
    codes = [c["code"] for c in repo.list_user_courses(user["id"])]
    return OSUClassSearch().recommend_next(codes)


# ================================ admin ====================================
@router.get("/api/admin/recruiters")
def list_recruiters(req: Request):
    req.require_roles("admin")
    return repo.list_registered_recruiters()


@router.post("/api/admin/recruiters")
def register_recruiter(req: Request):
    user = req.require_roles("admin")
    _require(req.body, "email", "company")
    if repo.get_registered_recruiter(req.body["email"]):
        raise HttpError(409, "Recruiter already registered")
    rid = repo.add_registered_recruiter(req.body["email"], req.body["company"], user["email"])
    return {"status": 201, "id": rid, "email": req.body["email"], "company": req.body["company"]}
