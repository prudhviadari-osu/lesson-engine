"""Compile a student's own work into a submission bundle (ported from compile.js).

Honesty-by-design: reads only the lesson_answers table (the student's own
writing from the staged flow). It NEVER invents content, reports exactly what's
done and what's missing grouped by lesson, and gates "ready to submit" behind an
explicit REVIEW + CONSENT tied to a hash of the exact approved content (editing
an answer invalidates a prior consent).
"""
from __future__ import annotations

import hashlib
import json

from ..db import repository as repo
from ..web.framework import HttpError


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def compile_assignment(assignment_id: int, user_id: int | None = None) -> dict:
    asg = repo.get_assignment(assignment_id)
    if asg is None:
        raise HttpError(404, "assignment not found")

    rows = repo.list_answerable_blocks(assignment_id)
    lessons: dict[int, dict] = {}
    order: list[int] = []
    for r in rows:
        lid = r["lesson_id"]
        if lid not in lessons:
            lessons[lid] = {"lessonId": lid, "seq": r["lesson_seq"], "title": r["lesson_title"], "items": []}
            order.append(lid)
        ans = repo.get_answer_for_block(r["block_id"])
        payload = json.loads(r["payload_json"])
        label = payload.get("instruction") or payload.get("prompt") or f"Item {r['block_id']}"
        text = (ans["content_text"] if ans else "").strip()
        lessons[lid]["items"].append({
            "blockId": r["block_id"],
            "kind": "deliverable" if r["type"] == "draft" else "reflection",
            "label": label, "answer": text, "done": len(text) > 0,
        })

    lesson_list = [lessons[lid] for lid in order]
    all_items = [i for l in lesson_list for i in l["items"]]
    total_items = len(all_items)
    done_items = sum(1 for i in all_items if i["done"])
    deliverables = [i for i in all_items if i["kind"] == "deliverable"]
    deliverables_done = sum(1 for i in deliverables if i["done"])

    missing_by_lesson = []
    for l in lesson_list:
        missing = [{"kind": i["kind"], "label": i["label"]} for i in l["items"] if not i["done"]]
        if missing:
            missing_by_lesson.append({
                "lessonId": l["lessonId"], "title": l["title"],
                "lessonStarted": any(i["done"] for i in l["items"]), "missing": missing,
            })
    missing_flat = [i["label"] for i in all_items if not i["done"]]

    # Markdown bundle
    lines = [f"# {asg['title']}"]
    if asg.get("due_at"):
        lines.append(f"_Due: {asg['due_at']}_")
    lines.append("")
    summary = f"> Compiled by learning++ from your own answers. {done_items}/{total_items} items done"
    summary += (f" · {deliverables_done}/{len(deliverables)} deliverable(s) drafted." if deliverables else ".")
    lines.append(summary)
    lines.append("")
    for l in lesson_list:
        done = [i for i in l["items"] if i["done"]]
        if not done:
            continue
        lines.append(f"## {l['title']}")
        lines.append("")
        for it in done:
            prefix = "✍️ " if it["kind"] == "deliverable" else ""
            lines.append(f"**{prefix}{it['label']}**")
            lines.append("")
            lines.append(it["answer"])
            lines.append("")
    if missing_by_lesson:
        lines.append("---")
        n = len(missing_flat)
        lines.append(f"### Still to do ({n} item{'' if n == 1 else 's'})")
        lines.append("")
        for l in missing_by_lesson:
            started = "" if l["lessonStarted"] else " _(not started)_"
            lines.append(f"- **{l['title']}**{started}")
            for m in l["missing"]:
                pre = "✍️ (deliverable) " if m["kind"] == "deliverable" else ""
                lines.append(f"  - {pre}{m['label']}")
        lines.append("")

    compiled_text = "\n".join(lines)
    content_hash = _hash(compiled_text)

    consent = repo.latest_consent(assignment_id, user_id)
    consent_valid = bool(
        consent and consent["content_hash"] == content_hash
        and consent["reviewed"] == 1 and consent["consented"] == 1
    )
    complete = len(missing_flat) == 0

    return {
        "assignmentId": asg["id"], "title": asg["title"], "dueAt": asg.get("due_at"),
        "complete": complete,
        "totals": {"totalItems": total_items, "doneItems": done_items,
                   "deliverables": len(deliverables), "deliverablesDone": deliverables_done},
        "byLesson": lesson_list, "missing": missing_flat, "missingByLesson": missing_by_lesson,
        "compiledText": compiled_text, "contentHash": content_hash,
        "review": {
            "readyToSubmit": consent_valid,
            "reviewed": bool(consent and consent["content_hash"] == content_hash and consent["reviewed"] == 1),
            "consented": bool(consent and consent["content_hash"] == content_hash and consent["consented"] == 1),
            "consentStale": bool(consent and consent["content_hash"] != content_hash),
        },
    }


def record_consent(assignment_id: int, user_id: int | None, reviewed: bool,
                   consented: bool, content_hash: str | None) -> dict:
    current = compile_assignment(assignment_id, user_id)
    if content_hash and content_hash != current["contentHash"]:
        raise HttpError(409, "content changed since you reviewed it — please review the updated submission again")
    repo.insert_consent(assignment_id, user_id, current["contentHash"],
                        1 if reviewed else 0, 1 if consented else 0)
    return compile_assignment(assignment_id, user_id)
