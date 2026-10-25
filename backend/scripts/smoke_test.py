"""End-to-end smoke test against a running Learn++ server (stdlib only).

Verifies the PRD Success Criteria: role-based login, course-scoped access,
recruiter restrictions, mini-lesson generation, forums, projects, profiles.

Run (server must be running):  python backend/scripts/smoke_test.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
PASSES = 0
FAILS = 0


def call(method, path, body=None, token=None, expect=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            status, payload = r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        status, payload = e.code, json.loads(e.read().decode() or "{}")
    return status, payload


def check(name, cond, detail=""):
    global PASSES, FAILS
    if cond:
        PASSES += 1
        print(f"  PASS  {name}")
    else:
        FAILS += 1
        print(f"  FAIL  {name}  {detail}")


def login(email, role, two_fa=False):
    s, p = call("POST", "/api/auth/login/verify",
                {"email": email, "password": "Password123", "role": role})
    if two_fa:
        s2, p2 = call("POST", "/api/auth/login/2fa", {"email": email, "code": "000000"})
        return p2["access_token"], p2["user"]
    s2, p2 = call("POST", "/api/auth/login",
                  {"email": email, "password": "Password123", "role": role})
    return p2["access_token"], p2["user"]


def main():
    print("== Health ==")
    s, p = call("GET", "/api/health")
    check("health ok", s == 200 and p["status"] == "ok", str(p))

    print("== Student login via OSU 2FA ==")
    stu_tok, stu = login("buckeye.1@osu.edu", "student", two_fa=True)
    check("student logged in", bool(stu_tok) and stu["role"] == "student")

    # wrong role on login should fail
    s, p = call("POST", "/api/auth/login",
                {"email": "buckeye.1@osu.edu", "password": "Password123", "role": "professor"})
    check("role mismatch rejected", s == 403, str(p))

    print("== Student courses (Canvas-synced) ==")
    s, courses = call("GET", "/api/courses", token=stu_tok)
    check("student has courses", s == 200 and len(courses) >= 3, str(courses))
    cse = next((c for c in courses if c["code"] == "CSE 2221"), None)
    check("CSE 2221 present", cse is not None)

    print("== Assignments + auto-decomposed interactive lessons ==")
    s, assigns = call("GET", f"/api/courses/{cse['id']}/assignments", token=stu_tok)
    check("assignments listed", s == 200 and len(assigns) >= 2, str(len(assigns)))
    with_lessons = [a for a in assigns if a.get("has_lessons")]
    check("lessons auto-decomposed", len(with_lessons) >= 1)

    aid = with_lessons[0]["id"]
    s, les = call("GET", f"/api/courses/{cse['id']}/assignments/{aid}/lessons", token=stu_tok)
    check("assignment has staged lessons", s == 200 and len(les["lessons"]) >= 1, str(s))
    lesson = les["lessons"][0]
    lid = lesson["id"]
    block_types = {b["type"] for b in lesson["blocks"]}
    check("lesson decomposed into typed blocks", len(lesson["blocks"]) >= 2 and block_types, str(block_types))

    print("== Gamified staged flow ==")
    s, flow = call("GET", f"/api/lessons/{lid}/flow", token=stu_tok)
    stage_types = [st["type"] for st in flow["stages"]]
    check("flow derives stages", s == 200 and "intro" in stage_types and "complete" in stage_types, str(stage_types))
    check("flow reports gamification", "totalXp" in flow["gamification"] and "dailyGoal" in flow["gamification"])

    s, r = call("POST", f"/api/lessons/{lid}/flow/advance", {"stageKey": "intro"}, token=stu_tok)
    check("intro stage awards XP", s == 200 and r["xpAwarded"] > 0, str(r))
    s, r2 = call("POST", f"/api/lessons/{lid}/flow/advance", {"stageKey": "intro"}, token=stu_tok)
    check("re-advancing a stage is idempotent (no double XP)", s == 200 and r2["xpAwarded"] == 0 and r2["alreadyDone"])

    challenge = next((st for st in flow["stages"] if st.get("challengeKind") == "scaffold"), None)
    if challenge:
        s, r = call("POST", f"/api/lessons/{lid}/flow/challenge",
                    {"stageKey": challenge["key"], "answer": "In my own words: the task is to reason about the contract."},
                    token=stu_tok)
        check("challenge awards XP + saves an answer", s == 200 and r["xpAwarded"] > 0 and r["savedToAnswer"], str(r))
        check("challenge returns Coach feedback (mock offline)", bool(r.get("feedback")))

    print("== Interactive Coach tutor (offline mock) ==")
    s, r = call("POST", f"/api/lessons/{lid}/tutor/start", {}, token=stu_tok)
    check("tutor start returns a Coach opening", s == 200 and len(r["history"]) >= 1 and bool(r["history"][0]["content"]))
    s, r = call("POST", f"/api/lessons/{lid}/tutor", {"message": "just give me the answer"}, token=stu_tok)
    check("Coach refuses to hand over the answer", s == 200 and ("won" in r["reply"].lower() or "step" in r["reply"].lower()))

    print("== Draft stage + compile ==")
    # Find (or decompose to reach) a draft stage in some lesson of this assignment.
    draft_lid, draft_stage = None, None
    for l in les["lessons"]:
        s, f = call("GET", f"/api/lessons/{l['id']}/flow", token=stu_tok)
        d = next((st for st in f["stages"] if st["type"] == "draft"), None)
        if d:
            draft_lid, draft_stage = l["id"], d
            break
    if draft_stage:
        s, r = call("POST", f"/api/lessons/{draft_lid}/flow/draft",
                    {"stageKey": draft_stage["key"], "content": "My own first draft of the deliverable."},
                    token=stu_tok)
        check("draft saves + awards XP + Coach feedback", s == 200 and r["xpAwarded"] > 0 and bool(r["feedback"]), str(r))

    s, comp = call("GET", f"/api/courses/{cse['id']}/assignments/{aid}/compile", token=stu_tok)
    check("compile reflects saved work", s == 200 and comp["totals"]["doneItems"] >= 1, str(comp["totals"]))
    check("compile not ready before consent", comp["review"]["readyToSubmit"] is False)

    print("== Review + consent gate ==")
    s, r = call("POST", f"/api/courses/{cse['id']}/assignments/{aid}/compile/consent",
                {"reviewed": True, "consented": True, "contentHash": comp["contentHash"]}, token=stu_tok)
    check("consent makes it ready to submit", s == 200 and r["review"]["readyToSubmit"] is True, str(r["review"]))
    # Editing an answer makes consent stale.
    if challenge:
        call("POST", f"/api/lessons/{lid}/flow/challenge",
             {"stageKey": challenge["key"], "answer": "A substantially edited answer that changes the content hash."},
             token=stu_tok)
    s, comp2 = call("GET", f"/api/courses/{cse['id']}/assignments/{aid}/compile", token=stu_tok)
    check("editing an answer makes consent stale", comp2["review"]["consentStale"] is True and comp2["review"]["readyToSubmit"] is False)
    s, r = call("POST", f"/api/courses/{cse['id']}/assignments/{aid}/compile/consent",
                {"reviewed": True, "consented": True, "contentHash": comp["contentHash"]}, token=stu_tok)
    check("stale-hash consent is rejected (409)", s == 409, str(s))

    print("== Learning-style preferences (max 2 + notes) ==")
    s, r = call("PUT", "/api/users/me/preferences",
                {"learningStyles": ["visual", "kinesthetic"], "learningNotes": "diagrams + hands-on"}, token=stu_tok)
    check("preferences saved", s == 200 and r["learningStyles"] == ["visual", "kinesthetic"], str(r))
    s, r = call("PUT", "/api/users/me/preferences",
                {"learningStyles": ["visual", "auditory", "reading"]}, token=stu_tok)
    check("more than 2 styles rejected", s == 400, str(s))

    print("== Planner + reflow (schedule / backlog) ==")
    s, plan = call("POST", "/api/plan/reflow", token=stu_tok)
    check("reflow schedules lessons", s == 200 and (len(plan["days"]) >= 1 or len(plan["unscheduled"]) >= 1), str(s))
    sched = [l for d in plan["days"] for l in d["lessons"]]
    if sched:
        target = sched[0]["lesson_id"]
        s, r = call("POST", f"/api/plan/lessons/{target}/unschedule", token=stu_tok)
        check("unschedule a lesson", s == 200 and r["ok"] is True)
        s, plan2 = call("GET", "/api/plan", token=stu_tok)
        check("unscheduled lesson is in the backlog", any(b["lesson_id"] == target for b in plan2["unscheduled"]))
    s, r = call("POST", "/api/plan/reflow", token=None)
    check("planner requires auth", s == 401, str(s))

    print("== Forums (course-scoped) ==")
    s, p = call("POST", f"/api/courses/{cse['id']}/forum/threads",
                {"title": "Test thread", "body": "hi"}, token=stu_tok)
    check("student can create thread", s == 201, str(p))
    tid = p["id"]
    s, p = call("POST", f"/api/courses/{cse['id']}/forum/threads/{tid}/posts",
                {"body": "a reply"}, token=stu_tok)
    check("student can reply", s == 201, str(p))

    print("== Professor moderation (own course only) ==")
    prof_tok, prof = login("weide.1@osu.edu", "professor", two_fa=True)
    s, threads = call("GET", f"/api/courses/{cse['id']}/forum/threads", token=prof_tok)
    check("prof sees course threads", s == 200 and len(threads) >= 1)
    # find a post to moderate
    post_id = None
    for t in threads:
        for po in t["posts"]:
            post_id = po["id"]
            break
        if post_id:
            break
    if post_id:
        s, p = call("POST", f"/api/courses/{cse['id']}/forum/posts/{post_id}/moderate",
                    {"hide": True}, token=prof_tok)
        check("prof can hide a post", s == 200 and p["hidden"] is True, str(p))

    # professor from a DIFFERENT course can't moderate here
    gomez_tok, _ = login("gomez.2@osu.edu", "professor", two_fa=True)
    if post_id:
        s, p = call("POST", f"/api/courses/{cse['id']}/forum/posts/{post_id}/moderate",
                    {"hide": True}, token=gomez_tok)
        check("other prof blocked from moderating", s == 403, str(p))

    print("== Recruiter restrictions ==")
    rec_tok, rec = login("recruiter.google@learnpp.test", "recruiter")
    s, p = call("GET", "/api/courses", token=rec_tok)
    check("recruiter sees no courses", s == 200 and p == [], str(p))
    s, p = call("GET", f"/api/courses/{cse['id']}/forum/threads", token=rec_tok)
    check("recruiter blocked from forums", s == 403, str(p))
    s, p = call("GET", "/api/projects/showcase", token=rec_tok)
    check("recruiter CAN see showcase projects", s == 200 and len(p) >= 1, str(p))

    print("== Unregistered recruiter signup blocked ==")
    s, p = call("POST", "/api/auth/signup", {
        "email": "random@evil.test", "username": "evilrec", "full_name": "Evil Rec",
        "password": "Password123", "role": "recruiter"})
    check("unregistered recruiter rejected", s == 403, str(p))

    print("== Schedule advisor (student only) ==")
    s, recs = call("GET", "/api/advisor/recommendations", token=stu_tok)
    check("advisor returns recommendations", s == 200 and len(recs) >= 1, str(recs))
    s, p = call("GET", "/api/advisor/recommendations", token=rec_tok)
    check("recruiter blocked from advisor", s == 403, str(p))

    print("== Profile customization (no social media) ==")
    s, p = call("PUT", "/api/users/me",
                {"bio": "Updated", "linkedin_url": "https://linkedin.com/in/jordan"}, token=stu_tok)
    check("profile update ok", s == 200 and p["bio"] == "Updated", str(p))
    s, p = call("PUT", "/api/users/me",
                {"github_url": "https://instagram.com/jordan"}, token=stu_tok)
    check("social media link rejected", s == 400, str(p))

    print("== Admin recruiter registry ==")
    admin_tok, _ = login("admin@osu.edu", "admin")
    s, p = call("POST", "/api/admin/recruiters",
                {"email": "recruiter.new@learnpp.test", "company": "NewCo"}, token=admin_tok)
    check("admin registers recruiter", s == 201, str(p))
    s, p = call("GET", "/api/admin/recruiters", token=admin_tok)
    check("admin lists recruiters", s == 200 and len(p) >= 7, str(len(p)))
    s, p = call("GET", "/api/admin/recruiters", token=stu_tok)
    check("student blocked from admin", s == 403, str(p))

    print("== Projects: student publishes showcase ==")
    s, p = call("POST", "/api/projects/showcase",
                {"title": "My App", "description": "cool", "tech_stack": "Python"}, token=stu_tok)
    check("student publishes showcase", s == 201, str(p))
    s, p = call("POST", "/api/projects/showcase",
                {"title": "Recruiter App"}, token=rec_tok)
    check("recruiter cannot publish", s == 403, str(p))

    print("== Portfolio (skills from completed work + guide + get help) ==")
    # Ensure the demo student has COMPLETED work (a 'done' lesson) to build on —
    # the same honesty-by-design basis compile uses. Complete one lesson's flow.
    s, r = call("POST", f"/api/lessons/{lid}/flow/complete", token=stu_tok)
    check("completed a lesson for portfolio evidence", s == 200 and r["lessonComplete"] is True, str(s))

    # Personal Portfolio: skills + completed work + stats (pure DB read, offline).
    s, pf = call("GET", "/api/portfolio", token=stu_tok)
    check("portfolio returns skills+completedWork+stats",
          s == 200 and "skills" in pf and len(pf["completedWork"]) >= 1
          and "totalXp" in pf["stats"], str(s))

    # Refresh extracts resume-worthy skills (mock offline) and is idempotent.
    s, rsk1 = call("POST", "/api/portfolio/skills/refresh", token=stu_tok)
    check("skills refresh extracts skills (mock offline)",
          s == 200 and rsk1["extracted"] >= 1 and len(rsk1["skills"]) >= 1, str(rsk1))
    s, rsk2 = call("POST", "/api/portfolio/skills/refresh", token=stu_tok)
    check("skills refresh is idempotent (no duplicates)",
          s == 200 and len(rsk2["skills"]) == len(rsk1["skills"]), str(len(rsk2["skills"])))

    # The Guide: AI-recommended projects (mock offline), honoring ?count=.
    s, guide = call("GET", "/api/portfolio/guide?count=3", token=stu_tok)
    check("guide recommends projects (mock offline)",
          s == 200 and len(guide["projects"]) >= 1 and bool(guide["projects"][0]["name"]), str(s))

    # "Get Help": materialize the project into a REAL gamified staged lesson flow.
    proj = guide["projects"][0]
    s, help1 = call("POST", "/api/portfolio/projects/help", {"project": proj}, token=stu_tok)
    check("get-help materializes a self-assigned assignment + lessons",
          s == 200 and help1["assignmentId"] and len(help1["lessons"]) >= 1, str(s))
    # Reachable through the normal staged-flow endpoint (proves it's a real lesson).
    help_lid = help1["lessons"][0]["id"]
    s, hflow = call("GET", f"/api/lessons/{help_lid}/flow", token=stu_tok)
    hstages = [st["type"] for st in hflow.get("stages", [])]
    check("get-help lesson is a playable staged flow",
          s == 200 and "intro" in hstages and "complete" in hstages, str(hstages))
    # Idempotent: asking for help again reuses the same assignment (no duplicate).
    s, help2 = call("POST", "/api/portfolio/projects/help", {"project": proj}, token=stu_tok)
    check("get-help is idempotent (reuses the assignment)",
          s == 200 and help2["reused"] is True and help2["assignmentId"] == help1["assignmentId"], str(help2))

    # Save a recommended project + update its status (PUT; framework has no PATCH).
    s, saved = call("POST", "/api/portfolio/projects",
                    {"project": {"name": "Smoke Test Portfolio App", "difficulty": "Beginner"}},
                    token=stu_tok)
    check("save a portfolio project", s in (200, 201) and saved.get("id"), str(s))
    s, upd = call("PUT", f"/api/portfolio/projects/{saved['id']}", {"status": "done"}, token=stu_tok)
    check("update a saved project's status", s == 200 and upd["status"] == "done", str(upd))
    s, bad = call("PUT", f"/api/portfolio/projects/{saved['id']}", {"status": "nonsense"}, token=stu_tok)
    check("invalid project status rejected", s == 400, str(s))

    # Portfolio is STUDENT-only (acts on the caller's own id; no client-supplied id).
    s, _ = call("GET", "/api/portfolio", token=rec_tok)
    check("recruiter blocked from portfolio", s == 403, str(s))

    print(f"\n==== {PASSES} passed, {FAILS} failed ====")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
