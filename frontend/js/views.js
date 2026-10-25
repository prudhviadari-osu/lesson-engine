/* Learn++ view renderers. Each returns an HTML string or renders into #view. */
const Views = (() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }
  function daysUntil(iso) {
    const ms = new Date(iso) - new Date();
    return Math.ceil(ms / 86400000);
  }
  function duePill(iso) {
    const d = daysUntil(iso);
    if (d < 0) return `<span class="pill">past due</span>`;
    const cls = d <= 2 ? "due" : d <= 7 ? "soon" : "";
    return `<span class="pill ${cls}">due in ${d} day${d === 1 ? "" : "s"}</span>`;
  }

  // ---------------- HOME ----------------
  async function home(user) {
    const courses = await API.get("/courses").catch(() => []);
    let dueSoon = [];
    for (const c of courses) {
      const as = await API.get(`/courses/${c.id}/assignments`).catch(() => []);
      as.forEach((a) => { if (daysUntil(a.due_at) >= 0 && daysUntil(a.due_at) <= 7) dueSoon.push({ ...a, course: c }); });
    }
    dueSoon.sort((a, b) => new Date(a.due_at) - new Date(b.due_at));

    const greeting = `Welcome back, ${esc(user.full_name.split(" ")[0])}!`;
    let html = `<div class="card"><h3>${greeting}</h3>
      <p class="muted">Role: <strong style="text-transform:capitalize">${esc(user.role)}</strong>${user.company ? " · " + esc(user.company) : ""}</p></div>`;

    if (user.role === "recruiter") {
      html += `<div class="card"><h3>Recruiter access</h3>
        <p class="muted">You have access to the <a href="#" data-nav="projects">student project showcase</a>. Course content is restricted.</p></div>`;
      return html;
    }

    html += `<div class="section-title"><h3 style="margin:0">Due in the next 7 days</h3></div>`;
    if (!dueSoon.length) {
      html += `<div class="empty">Nothing due soon. 🎉</div>`;
    } else {
      html += `<div class="stack">` + dueSoon.map((a) => `
        <div class="card" style="margin:0">
          <div class="row" style="justify-content:space-between">
            <div><strong>${esc(a.title)}</strong><div class="muted-row">${esc(a.course.code)} · ${esc(a.kind)}</div></div>
            <div class="row">${duePill(a.due_at)}
              <button class="btn sm" data-lesson-assignment="${a.id}" data-course="${a.course.id}">${a.has_lessons ? "Start lessons" : "Generate lessons"}</button>
            </div>
          </div>
        </div>`).join("") + `</div>`;
    }
    return html;
  }

  // ---------------- COURSES / LESSONS ----------------
  async function courses(user) {
    const list = await API.get("/courses").catch(() => []);
    if (!list.length) return `<div class="empty">You have no courses.</div>`;
    let html = `<div class="grid">`;
    for (const c of list) {
      const members = await API.get(`/courses/${c.id}/members`).catch(() => []);
      html += `<div class="card">
        <h3>${esc(c.code)}</h3>
        <div class="muted-row">${esc(c.title)}</div>
        <div class="muted-row">Section ${esc(c.section)} · ${esc(c.term)} · ${members.length} members</div>
        <div class="row" style="margin-top:12px">
          <button class="btn sm" data-course-assignments="${c.id}">Assignments & lessons</button>
          <button class="btn sm ghost" data-course-forum="${c.id}">Forum</button>
        </div>
      </div>`;
    }
    return html + `</div>`;
  }

  async function courseAssignments(courseId) {
    const as = await API.get(`/courses/${courseId}/assignments`);
    let html = `<button class="btn ghost sm" data-nav="courses">← Courses</button><div style="height:14px"></div>`;
    if (!as.length) return html + `<div class="empty">No assignments.</div>`;
    html += `<div class="stack">`;
    for (const a of as) {
      html += `<div class="card" style="margin:0">
        <div class="row" style="justify-content:space-between">
          <div><strong>${esc(a.title)}</strong><div class="muted-row">${esc(a.kind)} · ${esc(a.description)}</div></div>
          ${duePill(a.due_at)}
        </div>
        <div class="row" style="margin-top:10px">
          <button class="btn sm" data-lesson-assignment="${a.id}" data-course="${courseId}">
            ${a.has_lessons ? "Start lessons" : "Generate lessons"}</button>
          <button class="btn sm ghost" data-compile="${a.id}" data-course="${courseId}">Compile & submit</button>
          ${a.has_lessons ? `<span class="pill ok">${a.lessons.length} lesson${a.lessons.length === 1 ? "" : "s"} ready</span>` : ""}
        </div>
      </div>`;
    }
    return html + `</div>`;
  }

  // Lesson picker for an assignment (the decomposed sequence of lessons).
  async function lessonPicker(courseId, assignmentId) {
    const data = await API.assignmentLessons(courseId, assignmentId);
    let html = `<button class="btn ghost sm" data-course-assignments="${courseId}">← Assignments</button><div style="height:14px"></div>`;
    html += `<div class="card"><h3>${esc(data.title)}</h3>
      <p class="muted">Work through these bite-size lessons. Each one teaches a concept, then guides you to produce a piece of the real deliverable in your own words.</p></div>`;
    html += `<div class="stack">`;
    (data.lessons || []).forEach((l, i) => {
      html += `<div class="card" style="margin:0"><div class="row" style="justify-content:space-between">
        <div><strong>Lesson ${i + 1}: ${esc(l.title)}</strong>
          <div class="muted-row">~${esc(l.est_minutes)} min · ${l.blocks.length} activities${l.status === "done" ? " · ✅ done" : ""}</div></div>
        <button class="btn sm" data-lesson-flow="${l.id}" data-course="${courseId}" data-assignment="${assignmentId}">
          ${l.status === "done" ? "Review" : "Start"}</button>
      </div></div>`;
    });
    return html + `</div>`;
  }

  // -------- The interactive staged-flow player (renders into #view) --------
  async function lessonFlow(root, courseId, assignmentId, lessonId) {
    let state = { stageIdx: 0 };

    async function load() {
      const flow = await API.flow(lessonId);
      // Start at the first not-done stage (resume), else stage 0.
      const firstTodo = flow.stages.findIndex((s) => !s.done);
      state.stageIdx = firstTodo === -1 ? 0 : firstTodo;
      render(flow);
    }

    function header(flow) {
      const g = flow.gamification;
      return `<div class="flow-header">
        <button class="btn ghost sm" data-lesson-assignment="${assignmentId}" data-course="${courseId}">← Lessons</button>
        <div class="flow-title" style="margin-top:10px">${esc(flow.lessonTitle)}</div>
        <div class="xp-bar-wrap">
          <span class="xp-badge">⭐ ${g.totalXp} XP</span>
          <span class="streak-badge">🔥 ${g.todayStreak} today</span>
          <span class="muted" style="font-size:.8rem">Progress</span>
          <div class="progress-track"><div class="progress-fill" style="width:${flow.progress.progressPct}%"></div></div>
          <span class="muted" style="font-size:.8rem">${flow.progress.progressPct}%</span>
        </div>
        <div class="xp-bar-wrap">
          <span class="muted" style="font-size:.8rem">Daily goal ${g.dailyXp}/${g.dailyGoal}</span>
          <div class="goal-track"><div class="goal-fill" style="width:${g.dailyGoalPct}%"></div></div>
          ${g.dailyGoalMet ? `<span class="pill ok">goal met 🎉</span>` : ""}
        </div>
        <div class="stage-rail">${flow.stages.map((s, i) =>
          `<div class="stage-dot ${s.done ? "done" : ""} ${i === state.stageIdx ? "current" : ""}" data-stage-jump="${i}" title="${esc(s.title)}">${s.done ? "✓" : i + 1}</div>`).join("")}</div>
      </div>`;
    }

    function stageBody(flow) {
      const s = flow.stages[state.stageIdx];
      if (!s) return `<div class="empty">No stage.</div>`;
      const xp = `<span class="pill stage-xp">+${s.xp} XP</span>`;
      let inner = "";
      if (s.type === "intro") {
        inner = `<span class="stage-kind">Intro</span>${xp}<h3>${esc(s.title)}</h3>
          <p>${esc(s.body || "")}</p>
          <div class="stage-nav"><span></span>
            <button class="btn" data-advance="${esc(s.key)}">Let's go →</button></div>`;
      } else if (s.type === "video") {
        const p = s.payload || {};
        const embed = p.embedUrl
          ? `<iframe class="embed-video" src="${esc(p.embedUrl)}" allowfullscreen></iframe>`
          : `<p class="muted">No embedded video available offline. <a href="${esc(p.url)}" target="_blank" rel="noopener">Search YouTube for this topic →</a></p>`;
        inner = `<span class="stage-kind">Watch</span>${xp}<h3>${esc(p.title || "Watch a short teaching video")}</h3>
          ${embed}
          <div class="stage-nav"><span></span>
            <button class="btn" data-advance="${esc(s.key)}">I watched it ✓</button></div>`;
      } else if (s.type === "reading") {
        const p = s.payload || {};
        const body = p.resolved && p.text
          ? `<div class="reading-box">${esc(p.text)}</div>${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">Read more →</a>` : ""}`
          : `<p class="muted">Reading not fetched offline. <a href="${esc(p.url)}" target="_blank" rel="noopener">Look up this topic →</a></p>`;
        inner = `<span class="stage-kind">Read</span>${xp}<h3>${esc(p.heading || "Read the excerpt")}</h3>
          ${body}
          <div class="stage-nav"><span></span>
            <button class="btn" data-advance="${esc(s.key)}">I read it ✓</button></div>`;
      } else if (s.type === "challenge") {
        const saved = s.savedAnswer ? esc(s.savedAnswer) : "";
        inner = `<span class="stage-kind">Challenge</span>${xp}<h3>${esc(s.prompt || "Quick challenge")}</h3>
          ${s.hint ? `<p class="muted">💡 Hint: ${esc(s.hint)}</p>` : ""}
          <textarea class="input" id="challenge-input" rows="3" placeholder="Type your answer in your own words...">${saved}</textarea>
          <div id="challenge-feedback"></div>
          <div class="stage-nav">
            <button class="btn ghost" data-stage-prev>← Back</button>
            <button class="btn" data-challenge="${esc(s.key)}">Submit answer</button>
          </div>`;
      } else if (s.type === "draft") {
        const saved = s.savedAnswer ? esc(s.savedAnswer) : "";
        inner = `<span class="stage-kind">Draft</span>${xp}<h3>${esc(s.prompt || "Draft the deliverable")}</h3>
          ${s.rubricHint ? `<p class="muted">📋 ${esc(s.rubricHint)}</p>` : ""}
          <p class="muted" style="font-size:.82rem">This is YOUR work — Coach gives feedback but never writes it for you.</p>
          <textarea class="input" id="draft-input" rows="6" placeholder="Write your own draft here...">${saved}</textarea>
          <div id="draft-feedback"></div>
          <div class="stage-nav">
            <button class="btn ghost" data-stage-prev>← Back</button>
            <button class="btn" data-draft="${esc(s.key)}">Save draft + get feedback</button>
          </div>`;
      } else if (s.type === "complete") {
        inner = `<div class="celebrate"><div class="big">🎉</div>
          <h3>Lesson complete!</h3>
          <p class="muted">Great work — you built real understanding, in your own words.</p>
          <div style="height:12px"></div>
          <button class="btn" data-complete>Finish & claim bonus (+${s.xp} XP)</button></div>`;
      }
      return `<div class="stage-card">${inner}</div>`;
    }

    function coach(flow) {
      return `<div class="coach-panel">
        <div class="coach-head"><strong>🧑‍🏫 Coach</strong>
          <button class="btn ghost sm" data-coach-reset>Restart chat</button></div>
        <div class="coach-msgs" id="coach-msgs"><div class="muted" style="margin:auto">Tap "Ask Coach" to start a conversation.</div></div>
        <div class="coach-input">
          <input class="input" id="coach-text" placeholder="Ask Coach anything about this lesson..." />
          <button class="btn" data-coach-send>Send</button>
          <button class="btn ghost" data-coach-start>Ask Coach</button>
        </div>
      </div>`;
    }

    function render(flow) {
      root.innerHTML = header(flow) + stageBody(flow) + coach(flow);
      wire(flow);
    }

    function setFeedback(id, text, cls) {
      const el = document.getElementById(id);
      if (el) el.innerHTML = `<div class="feedback-box ${cls || ""}">${esc(text)}</div>`;
    }

    function renderCoach(history) {
      const box = document.getElementById("coach-msgs");
      if (!box) return;
      if (!history.length) { box.innerHTML = `<div class="muted" style="margin:auto">No messages yet.</div>`; return; }
      box.innerHTML = history.map((m) => `<div class="coach-msg ${m.role === "model" ? "model" : "user"}">${esc(m.content)}</div>`).join("");
      box.scrollTop = box.scrollHeight;
    }

    function wire(flow) {
      root.querySelectorAll("[data-stage-jump]").forEach((d) =>
        d.onclick = () => { state.stageIdx = Number(d.dataset.stageJump); render(flow); });
      const prev = root.querySelector("[data-stage-prev]");
      if (prev) prev.onclick = () => { if (state.stageIdx > 0) state.stageIdx--; render(flow); };

      root.querySelectorAll("[data-advance]").forEach((b) => b.onclick = async () => {
        b.disabled = true;
        try { await API.flowAdvance(lessonId, b.dataset.advance); state.stageIdx++; await load(); }
        catch (e) { window.toast(e.message, true); b.disabled = false; }
      });

      const chalBtn = root.querySelector("[data-challenge]");
      if (chalBtn) chalBtn.onclick = async () => {
        const answer = document.getElementById("challenge-input").value.trim();
        if (!answer) return window.toast("Type an answer first", true);
        chalBtn.disabled = true;
        try {
          const r = await API.flowChallenge(lessonId, chalBtn.dataset.challenge, answer);
          const cls = r.correct === true ? "correct" : r.correct === false ? "tryagain" : "";
          setFeedback("challenge-feedback",
            (r.revealed ? `Answer: ${r.revealed}\n\n` : "") + (r.feedback || "Saved!"), cls);
          if (r.xpAwarded > 0) window.toast(`+${r.xpAwarded} XP!`);
          // refresh header XP + stage done state, stay on stage to read feedback
          const flow2 = await API.flow(lessonId);
          root.querySelector(".flow-header").outerHTML = header(flow2);
          wire(flow2);
          // restore feedback (header rewrite wiped it)
          const cls2 = r.correct === true ? "correct" : r.correct === false ? "tryagain" : "";
          setFeedback("challenge-feedback",
            (r.revealed ? `Answer: ${r.revealed}\n\n` : "") + (r.feedback || "Saved!"), cls2);
        } catch (e) { window.toast(e.message, true); } finally { chalBtn.disabled = false; }
      };

      const draftBtn = root.querySelector("[data-draft]");
      if (draftBtn) draftBtn.onclick = async () => {
        const content = document.getElementById("draft-input").value.trim();
        if (!content) return window.toast("Write your draft first", true);
        draftBtn.disabled = true;
        try {
          const r = await API.flowDraft(lessonId, draftBtn.dataset.draft, content);
          setFeedback("draft-feedback", r.feedback || "Draft saved!");
          if (r.xpAwarded > 0) window.toast(`+${r.xpAwarded} XP!`);
          const flow2 = await API.flow(lessonId);
          root.querySelector(".flow-header").outerHTML = header(flow2);
          wire(flow2);
          setFeedback("draft-feedback", r.feedback || "Draft saved!");
        } catch (e) { window.toast(e.message, true); } finally { draftBtn.disabled = false; }
      };

      const done = root.querySelector("[data-complete]");
      if (done) done.onclick = async () => {
        done.disabled = true;
        try {
          const r = await API.flowComplete(lessonId);
          window.toast(r.completionBonus > 0 ? `Lesson done! +${r.completionBonus} XP 🎉` : "Lesson complete!");
          await load();
        } catch (e) { window.toast(e.message, true); done.disabled = false; }
      };

      // Coach chat
      const startBtn = root.querySelector("[data-coach-start]");
      if (startBtn) startBtn.onclick = async () => {
        startBtn.disabled = true;
        try { const r = await API.tutorStart(lessonId, false); renderCoach(r.history); }
        catch (e) { window.toast(e.message, true); } finally { startBtn.disabled = false; }
      };
      const resetBtn = root.querySelector("[data-coach-reset]");
      if (resetBtn) resetBtn.onclick = async () => {
        try { const r = await API.tutorStart(lessonId, true); renderCoach(r.history); } catch (e) { window.toast(e.message, true); }
      };
      const sendBtn = root.querySelector("[data-coach-send]");
      const sendFn = async () => {
        const inp = document.getElementById("coach-text");
        const msg = inp.value.trim();
        if (!msg) return;
        inp.value = "";
        sendBtn.disabled = true;
        try { const r = await API.tutorSend(lessonId, msg); renderCoach(r.history); }
        catch (e) { window.toast(e.message, true); } finally { sendBtn.disabled = false; }
      };
      if (sendBtn) sendBtn.onclick = sendFn;
      const coachText = document.getElementById("coach-text");
      if (coachText) coachText.onkeydown = (e) => { if (e.key === "Enter") sendFn(); };
    }

    root.innerHTML = `<div class="muted">Loading lesson…</div>`;
    await load();
  }

  // -------------- COMPILE + review/consent --------------
  async function compile(root, courseId, assignmentId) {
    async function load() {
      const c = await API.compile(courseId, assignmentId);
      render(c);
    }
    function render(c) {
      const r = c.review;
      let html = `<button class="btn ghost sm" data-course-assignments="${courseId}">← Assignments</button><div style="height:14px"></div>`;
      html += `<div class="card"><h3>${esc(c.title)}</h3>
        <div class="muted-row">${c.totals.doneItems}/${c.totals.totalItems} items done · ${c.totals.deliverablesDone}/${c.totals.deliverables} deliverable(s) drafted</div>
        <div class="progress-track" style="margin-top:10px"><div class="progress-fill" style="width:${c.totals.totalItems ? Math.round(c.totals.doneItems / c.totals.totalItems * 100) : 0}%"></div></div>
      </div>`;

      if (c.missingByLesson.length) {
        html += `<div class="card"><h3>Still to do</h3><ul class="missing-list">` +
          c.missingByLesson.map((l) => `<li><strong>${esc(l.title)}</strong>${l.lessonStarted ? "" : " <span class='muted'>(not started)</span>"}<ul>` +
            l.missing.map((m) => `<li>${m.kind === "deliverable" ? "✍️ " : ""}${esc(m.label)}</li>`).join("") + `</ul></li>`).join("") +
          `</ul></div>`;
      }

      html += `<div class="card"><h3>Your compiled submission</h3>
        <p class="muted">Assembled from YOUR OWN answers — nothing is invented.</p>
        <div class="compiled-md">${esc(c.compiledText)}</div></div>`;

      const cls = r.readyToSubmit ? "ready" : "";
      html += `<div class="consent-box ${cls}" id="consent-box">`;
      if (r.consentStale) html += `<p><strong>⚠️ You edited an answer since consenting.</strong> Please review the updated submission and consent again.</p>`;
      if (r.readyToSubmit) {
        html += `<p><strong>✅ Ready to submit.</strong> You've reviewed and consented to this exact content.</p>`;
      } else {
        html += `<p><strong>Review + consent required before submitting.</strong></p>
          <label class="consent-row"><input type="checkbox" id="c-reviewed" /> I have reviewed everything above and it reflects my own understanding.</label>
          <label class="consent-row"><input type="checkbox" id="c-consented" /> This is my own work and I consent to submit it.</label>
          <button class="btn" id="consent-btn" disabled>Mark ready to submit</button>`;
      }
      html += `</div>`;
      root.innerHTML = html;
      wire(c);
    }
    function wire(c) {
      const rev = document.getElementById("c-reviewed");
      const con = document.getElementById("c-consented");
      const btn = document.getElementById("consent-btn");
      const sync = () => { if (btn) btn.disabled = !(rev.checked && con.checked); };
      if (rev) rev.onchange = sync;
      if (con) con.onchange = sync;
      if (btn) btn.onclick = async () => {
        btn.disabled = true;
        try { await API.compileConsent(courseId, assignmentId, c.contentHash); window.toast("Marked ready to submit 🎉"); await load(); }
        catch (e) { window.toast(e.message, true); btn.disabled = false; }
      };
    }
    root.innerHTML = `<div class="muted">Compiling your work…</div>`;
    await load();
  }

  // -------------- PLANNER --------------
  async function plan() {
    const p = await API.plan();
    let html = `<div class="card"><div class="row" style="justify-content:space-between">
      <div><h3>Your study plan</h3>
        <p class="muted">Scheduled backward from each due date, ${p.dailyCapMin} min/day cap, ${p.submissionBufferDays}-day submission buffer.</p></div>
      <div class="row"><span class="streak-badge">🔥 ${p.todayStreak} today</span>
        <button class="btn sm" data-plan-reflow>Reflow</button></div>
    </div></div>`;
    if (!p.days.length) html += `<div class="empty">No scheduled lessons. Hit Reflow to build your plan.</div>`;
    p.days.forEach((d) => {
      html += `<div class="card" style="margin:0 0 12px"><div class="row" style="justify-content:space-between">
        <strong>${esc(d.date)}</strong>
        <span class="pill ${d.overCapacity ? "due" : "ok"}">${d.loadMinutes} min${d.overCapacity ? " · over cap" : ""}</span></div>
        <div class="stack" style="margin-top:8px">` +
        d.lessons.map((l) => `<div class="row" style="justify-content:space-between">
          <span>${esc(l.title)} <span class="muted">(~${l.est_minutes}m · ${esc(l.assignment)})</span></span>
          <button class="btn ghost sm" data-plan-unschedule="${l.lesson_id}">Unschedule</button></div>`).join("") +
        `</div></div>`;
    });
    html += `<div class="section-title"><h3 style="margin:0">Backlog</h3><span class="pill">unscheduled</span></div>`;
    if (!p.unscheduled.length) html += `<div class="empty">Backlog is empty.</div>`;
    else html += `<div class="stack">` + p.unscheduled.map((l) => `<div class="card" style="margin:0"><div class="row" style="justify-content:space-between">
      <span>${esc(l.title)} <span class="muted">(~${l.est_minutes}m · ${esc(l.assignment)})</span></span>
      <button class="btn sm" data-plan-reschedule="${l.lesson_id}">Schedule</button></div></div>`).join("") + `</div>`;
    return html;
  }

  // -------------- LEARNING PREFERENCES --------------
  async function preferences() {
    const p = await API.getPreferences();
    const STYLES = [["visual", "👁️ Visual"], ["auditory", "👂 Auditory"], ["reading", "📖 Reading/Writing"], ["kinesthetic", "✋ Kinesthetic"]];
    const selected = new Set(p.learningStyles);
    let html = `<div class="card"><h3>Learning style</h3>
      <p class="muted">Pick up to 2. We tailor your lessons and Coach to match — without ever changing the "do your own work" rules.</p>
      <div class="row" id="style-chips" style="margin-top:12px">` +
      STYLES.map(([k, label]) => `<span class="style-chip ${selected.has(k) ? "selected" : ""}" data-style="${k}">${esc(label)}</span>`).join("") +
      `</div>
      <label style="margin-top:16px">Anything specific? (optional)
        <textarea class="input" id="pref-notes" rows="3" placeholder="e.g. I like worked examples and short videos">${esc(p.learningNotes || "")}</textarea></label>
      <div style="margin-top:14px"><button class="btn" data-save-preferences>Save preferences</button></div>
    </div>`;
    return html;
  }

  // ---------------- FORUMS ----------------
  async function forum(courseId, user) {
    const threads = await API.get(`/courses/${courseId}/forum/threads`);
    let html = `<button class="btn ghost sm" data-nav="courses">← Courses</button><div style="height:14px"></div>`;
    html += `<div class="card"><h3>New discussion</h3>
      <div class="stack">
        <input class="input" id="thread-title" placeholder="Title" />
        <textarea class="input" id="thread-body" rows="2" placeholder="What's on your mind?"></textarea>
        <div><button class="btn sm" data-new-thread="${courseId}">Post thread</button></div>
      </div></div>`;
    if (!threads.length) html += `<div class="empty">No discussions yet.</div>`;
    threads.forEach((t) => {
      html += `<div class="card"><h3>${t.pinned ? "📌 " : ""}${esc(t.title)}</h3>
        <p>${esc(t.body)}</p>
        <div class="posts">` +
        (t.posts || []).map((p) => `<div class="post ${p.hidden ? "hidden-post" : ""}">
            ${esc(p.body)} ${p.hidden ? '<span class="badge-hidden">[hidden]</span>' : ""}
            ${(user.role === "professor" || user.role === "admin")
              ? `<button class="btn sm ghost" style="float:right" data-moderate="${p.id}" data-course="${courseId}" data-hide="${p.hidden ? 0 : 1}">${p.hidden ? "Unhide" : "Hide"}</button>` : ""}
          </div>`).join("") +
        `</div>
        <div class="row" style="margin-top:10px">
          <input class="input" id="reply-${t.id}" placeholder="Reply…" style="flex:1" />
          <button class="btn sm" data-reply="${t.id}" data-course="${courseId}">Reply</button>
        </div></div>`;
    });
    return html;
  }

  // ---------------- PROJECTS ----------------
  async function projects(user) {
    const showcase = await API.get("/projects/showcase").catch(() => []);
    let html = "";
    if (user.role === "student") {
      html += `<div class="card"><h3>Publish a project</h3>
        <div class="stack">
          <input class="input" id="proj-title" placeholder="Project title" />
          <textarea class="input" id="proj-desc" rows="2" placeholder="Description"></textarea>
          <input class="input" id="proj-repo" placeholder="GitHub repo URL (optional)" />
          <input class="input" id="proj-stack" placeholder="Tech stack (optional)" />
          <div><button class="btn sm" data-publish-project>Publish to showcase</button></div>
        </div></div>`;
    }
    html += `<div class="section-title"><h3 style="margin:0">Student Showcase</h3>
      <span class="pill">visible to recruiters</span></div>`;
    if (!showcase.length) html += `<div class="empty">No published projects yet.</div>`;
    showcase.forEach((p) => {
      html += `<div class="card"><h3>${esc(p.title)}</h3>
        <p>${esc(p.description)}</p>
        ${p.tech_stack ? `<div class="muted-row">🧰 ${esc(p.tech_stack)}</div>` : ""}
        ${p.repo_url ? `<div class="muted-row">🔗 <a href="${esc(p.repo_url)}" target="_blank" rel="noopener">${esc(p.repo_url)}</a></div>` : ""}
        <div class="comments">` +
        (p.comments || []).map((c) => `<div class="comment">${esc(c.body)}</div>`).join("") +
        `</div>
        <div class="row" style="margin-top:10px">
          <input class="input" id="comment-${p.id}" placeholder="Add a comment…" style="flex:1" />
          <button class="btn sm" data-comment="${p.id}">Comment</button>
        </div></div>`;
    });
    return html;
  }

  // ---------------- ANNOUNCEMENTS ----------------
  async function announcements(user) {
    const list = await API.get("/announcements").catch(() => []);
    let html = "";
    if (user.role === "professor" || user.role === "admin") {
      const courses = await API.get("/courses").catch(() => []);
      html += `<div class="card"><h3>New announcement</h3>
        <div class="stack">
          <input class="input" id="ann-title" placeholder="Title" />
          <textarea class="input" id="ann-body" rows="2" placeholder="Details"></textarea>
          <div class="row">
            <select class="input" id="ann-category" style="flex:1">
              <option value="event">Event</option><option value="study">Study session</option>
              <option value="exam">Exam</option><option value="resource">Resource</option>
            </select>
            <select class="input" id="ann-course" style="flex:1">
              <option value="">Organization-wide</option>
              ${courses.map((c) => `<option value="${c.id}">${esc(c.code)}</option>`).join("")}
            </select>
          </div>
          <input class="input" id="ann-location" placeholder="Location (Discord / room)" />
          <div><button class="btn sm" data-new-announcement>Post</button></div>
        </div></div>`;
    }
    if (!list.length) html += `<div class="empty">No announcements.</div>`;
    list.forEach((a) => {
      html += `<div class="card"><div class="row" style="justify-content:space-between">
          <h3 style="margin:0">${esc(a.title)}</h3><span class="pill">${esc(a.category)}</span></div>
        <p>${esc(a.body)}</p>
        <div class="muted-row">${a.location ? "📍 " + esc(a.location) + " · " : ""}${a.event_at ? "🗓️ " + fmtDate(a.event_at) : ""}</div>
      </div>`;
    });
    return html;
  }

  // ---------------- ADVISOR ----------------
  async function advisor() {
    const recs = await API.get("/advisor/recommendations").catch((e) => { throw e; });
    let html = `<div class="card"><h3>Schedule Advisor</h3>
      <p class="muted">Recommended courses for next semester, based on your current enrollment (OSU class search).</p></div>`;
    if (!recs.length) return html + `<div class="empty">No recommendations yet.</div>`;
    html += `<div class="grid">` + recs.map((r) => `<div class="card">
      <h3>${esc(r.code)}</h3><div class="muted-row">${esc(r.title)} · ${r.credit_hours} cr</div>
      <p style="margin:10px 0 0">${esc(r.reason)}</p></div>`).join("") + `</div>`;
    return html;
  }

  // ---------------- ADMIN ----------------
  async function admin() {
    const recs = await API.get("/admin/recruiters").catch(() => []);
    let html = `<div class="card"><h3>Authorized Recruiter Registry</h3>
      <p class="muted">Only recruiters on this list may create accounts and view the showcase.</p>
      <div class="stack" style="margin-top:10px">
        <div class="row">
          <input class="input" id="rec-email" placeholder="Recruiter email" style="flex:1" />
          <input class="input" id="rec-company" placeholder="Company" style="flex:1" />
          <button class="btn sm" data-add-recruiter>Add</button>
        </div>
      </div></div>`;
    html += `<div class="card"><table style="width:100%;border-collapse:collapse">
      <tr style="text-align:left;color:var(--muted)"><th>Email</th><th>Company</th></tr>` +
      recs.map((r) => `<tr><td style="padding:6px 0">${esc(r.email)}</td><td>${esc(r.company)}</td></tr>`).join("") +
      `</table></div>`;
    return html;
  }

  // ---------------- PROFILE ----------------
  async function profile() {
    const u = await API.get("/users/me");
    return `<div class="card"><h3>Edit profile</h3>
      <p class="muted">Add GitHub & LinkedIn. Social media links (Instagram, TikTok, YouTube) are not allowed.</p>
      <div class="stack" style="margin-top:10px">
        <label>Full name<input class="input" id="pf-name" value="${esc(u.full_name)}" /></label>
        <label>Bio<textarea class="input" id="pf-bio" rows="2">${esc(u.bio || "")}</textarea></label>
        <label>Major<input class="input" id="pf-major" value="${esc(u.major || "")}" /></label>
        <label>Graduation year<input class="input" id="pf-grad" type="number" value="${esc(u.grad_year || "")}" /></label>
        <label>Avatar URL<input class="input" id="pf-avatar" value="${esc(u.avatar_url || "")}" /></label>
        <label>GitHub<input class="input" id="pf-github" value="${esc(u.github_url || "")}" placeholder="https://github.com/you" /></label>
        <label>LinkedIn<input class="input" id="pf-linkedin" value="${esc(u.linkedin_url || "")}" placeholder="https://linkedin.com/in/you" /></label>
        <div><button class="btn" data-save-profile>Save profile</button></div>
      </div></div>`;
  }

  return {
    esc, home, courses, courseAssignments, lessonPicker, lessonFlow, compile,
    plan, preferences, forum, projects, announcements, advisor, admin, profile,
  };
})();
