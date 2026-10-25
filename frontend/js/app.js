/* Learn++ app controller: auth, routing, nav, and event wiring. */
(() => {
  const $ = (id) => document.getElementById(id);
  let pendingLogin = null; // {email, password, role}

  // Role-based navigation definitions.
  const NAV = {
    student: [
      ["home", "🏠", "Home"], ["courses", "📚", "Courses"], ["plan", "🗓️", "Plan"],
      ["portfolio", "🎓", "Portfolio"], ["projects", "💡", "Projects"],
      ["announcements", "📣", "Announcements"], ["advisor", "🧭", "Advisor"],
      ["preferences", "🎛️", "Learning"], ["profile", "👤", "Profile"],
    ],
    professor: [
      ["home", "🏠", "Home"], ["courses", "📚", "Courses"], ["projects", "💡", "Projects"],
      ["announcements", "📣", "Announcements"], ["profile", "👤", "Profile"],
    ],
    admin: [
      ["home", "🏠", "Home"], ["courses", "📚", "Courses"], ["announcements", "📣", "Announcements"],
      ["admin", "🛡️", "Recruiters"], ["profile", "👤", "Profile"],
    ],
    recruiter: [
      ["home", "🏠", "Home"], ["projects", "💡", "Showcase"], ["profile", "👤", "Profile"],
    ],
  };
  const TITLES = {
    home: "Home", courses: "Courses", plan: "Study Plan", lessonPicker: "Lessons",
    lessonFlow: "Lesson", compile: "Compile & Submit", preferences: "Learning Style",
    projects: "Projects", announcements: "Announcements", advisor: "Schedule Advisor",
    admin: "Recruiter Registry", profile: "Profile", portfolio: "Portfolio",
  };

  function toast(msg, isErr) {
    const t = document.createElement("div");
    t.className = "toast" + (isErr ? " err" : "");
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2600);
  }
  window.toast = toast;

  // ---------------- AUTH FLOW ----------------
  function showAuth() { $("auth-screen").classList.remove("hidden"); $("app-shell").classList.add("hidden"); }
  function showApp() { $("auth-screen").classList.add("hidden"); $("app-shell").classList.remove("hidden"); }

  function hideAllAuthForms() {
    ["role-picker", "login-form", "twofa-form", "signup-form"].forEach((i) => $(i).classList.add("hidden"));
  }

  document.querySelectorAll(".role-btn").forEach((b) => b.addEventListener("click", () => {
    pendingLogin = { role: b.dataset.role };
    $("login-role-label").textContent = b.textContent.trim();
    hideAllAuthForms(); $("login-form").classList.remove("hidden");
  }));
  $("back-to-roles").onclick = () => { hideAllAuthForms(); $("role-picker").classList.remove("hidden"); };
  $("to-signup").onclick = (e) => { e.preventDefault(); hideAllAuthForms(); $("signup-form").classList.remove("hidden"); };
  $("back-to-login").onclick = () => { hideAllAuthForms(); $("login-form").classList.remove("hidden"); };

  $("signup-role").onchange = (e) => {
    const isRec = e.target.value === "recruiter";
    $("signup-company").classList.toggle("hidden", !isRec);
    $("signup-osu").classList.toggle("hidden", isRec);
  };

  $("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("login-error").textContent = "";
    const email = $("login-email").value.trim();
    const password = $("login-password").value;
    const role = pendingLogin.role;
    pendingLogin = { email, password, role };
    try {
      const v = await API.loginVerify(email, password, role);
      if (v.requires_2fa) {
        $("twofa-msg").textContent = v.message || "Enter your OSU verification code.";
        hideAllAuthForms(); $("twofa-form").classList.remove("hidden");
      } else {
        const r = await API.login(email, password, role);
        API.setSession(r.access_token, r.user); enterApp();
      }
    } catch (err) { $("login-error").textContent = err.message; }
  });

  $("twofa-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("twofa-error").textContent = "";
    try {
      const r = await API.login2fa(pendingLogin.email, $("twofa-code").value.trim());
      API.setSession(r.access_token, r.user); enterApp();
    } catch (err) { $("twofa-error").textContent = err.message; }
  });

  $("signup-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("signup-error").textContent = "";
    const payload = {
      role: $("signup-role").value,
      full_name: $("signup-fullname").value.trim(),
      username: $("signup-username").value.trim(),
      email: $("signup-email").value.trim(),
      password: $("signup-password").value,
      osu_name_dot_number: $("signup-osu").value.trim() || null,
      company: $("signup-company").value.trim() || null,
    };
    try {
      const r = await API.signup(payload);
      API.setSession(r.access_token, r.user); enterApp();
    } catch (err) { $("signup-error").textContent = err.message; }
  });

  $("logout-btn").onclick = () => { API.clearSession(); showAuth(); hideAllAuthForms(); $("role-picker").classList.remove("hidden"); };

  // ---------------- NAV + ROUTING ----------------
  function buildNav(user) {
    const items = NAV[user.role] || NAV.student;
    const navHtml = items.map(([key, ico, label]) =>
      `<button class="nav-item" data-nav="${key}"><span class="nav-ico">${ico}</span><span class="nav-label">${label}</span></button>`).join("");
    $("nav").innerHTML = navHtml;
    // bottom bar: first 4 items for mobile
    $("bottombar").innerHTML = items.slice(0, 4).map(([key, ico, label]) =>
      `<button class="nav-item" data-nav="${key}"><span class="nav-ico">${ico}</span><span class="nav-label">${label}</span></button>`).join("");

    const av = $("side-avatar"); av.textContent = (user.full_name || "?").charAt(0).toUpperCase();
    $("side-name").textContent = user.full_name;
    $("side-role").textContent = user.role + (user.company ? " · " + user.company : "");
  }

  function setActive(key) {
    document.querySelectorAll(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.nav === key));
  }

  async function navigate(key, extra) {
    const user = API.currentUser();
    const view = $("view");
    $("page-title").textContent = TITLES[key] || "Learn++";
    setActive(key);
    view.innerHTML = `<div class="muted">Loading…</div>`;
    try {
      // Self-rendering async controllers render straight into #view.
      if (key === "lessonFlow") {
        await Views.lessonFlow(view, extra.courseId, extra.assignmentId, extra.lessonId);
        document.querySelector(".app-shell").classList.remove("mobile-open");
        return;
      }
      if (key === "compile") {
        await Views.compile(view, extra.courseId, extra.assignmentId);
        document.querySelector(".app-shell").classList.remove("mobile-open");
        return;
      }
      if (key === "portfolio") {
        await Views.portfolio(view, navigate);
        document.querySelector(".app-shell").classList.remove("mobile-open");
        return;
      }
      let html = "";
      switch (key) {
        case "home": html = await Views.home(user); break;
        case "courses": html = await Views.courses(user); break;
        case "plan": html = await Views.plan(); break;
        case "preferences": html = await Views.preferences(); break;
        case "courseAssignments": html = await Views.courseAssignments(extra.courseId); break;
        case "lessonPicker": html = await Views.lessonPicker(extra.courseId, extra.assignmentId); break;
        case "forum": html = await Views.forum(extra.courseId, user); break;
        case "projects": html = await Views.projects(user); break;
        case "announcements": html = await Views.announcements(user); break;
        case "advisor": html = await Views.advisor(); break;
        case "admin": html = await Views.admin(); break;
        case "profile": html = await Views.profile(); break;
      }
      view.innerHTML = html;
    } catch (err) {
      view.innerHTML = `<div class="empty">${Views.esc(err.message)}</div>`;
    }
    // close mobile drawer after nav
    document.querySelector(".app-shell").classList.remove("mobile-open");
  }

  function enterApp() {
    const user = API.currentUser();
    buildNav(user);
    showApp();
    navigate("home");
  }

  // ---------------- GLOBAL EVENT DELEGATION ----------------
  document.addEventListener("click", async (e) => {
    // Learning-style chips (toggle, max 2) — handled before the generic closest().
    const chip = e.target.closest("[data-style]");
    if (chip && chip.closest("#style-chips")) {
      const box = chip.closest("#style-chips");
      const selected = box.querySelectorAll(".style-chip.selected");
      if (!chip.classList.contains("selected") && selected.length >= 2) {
        return toast("Pick at most 2 styles", true);
      }
      chip.classList.toggle("selected");
      return;
    }

    const el = e.target.closest("[data-nav],[data-course-assignments],[data-course-forum],[data-lesson-assignment],[data-lesson-flow],[data-compile],[data-reply],[data-new-thread],[data-moderate],[data-comment],[data-publish-project],[data-new-announcement],[data-add-recruiter],[data-save-profile],[data-save-preferences],[data-plan-reflow],[data-plan-unschedule],[data-plan-reschedule]");
    if (!el) return;

    if (el.dataset.nav) return navigate(el.dataset.nav);
    if (el.dataset.courseAssignments) return navigate("courseAssignments", { courseId: el.dataset.courseAssignments });
    if (el.dataset.courseForum) return navigate("forum", { courseId: el.dataset.courseForum });
    if (el.dataset.lessonAssignment) return navigate("lessonPicker", { courseId: el.dataset.course, assignmentId: el.dataset.lessonAssignment });
    if (el.dataset.lessonFlow) return navigate("lessonFlow", { courseId: el.dataset.course, assignmentId: el.dataset.assignment, lessonId: el.dataset.lessonFlow });
    if (el.dataset.compile !== undefined && el.dataset.compile) return navigate("compile", { courseId: el.dataset.course, assignmentId: el.dataset.compile });

    try {
      if (el.dataset.planReflow !== undefined) { await API.planReflow(); toast("Plan reflowed"); return navigate("plan"); }
      if (el.dataset.planUnschedule) { await API.planUnschedule(el.dataset.planUnschedule); toast("Moved to backlog"); return navigate("plan"); }
      if (el.dataset.planReschedule) { await API.planReschedule(el.dataset.planReschedule); toast("Scheduled"); return navigate("plan"); }
      if (el.dataset.savePreferences !== undefined) {
        const styles = [...document.querySelectorAll("#style-chips .style-chip.selected")].map((c) => c.dataset.style);
        await API.setPreferences(styles, document.getElementById("pref-notes").value);
        toast("Preferences saved"); return navigate("preferences");
      }
      if (el.dataset.newThread) {
        const cid = el.dataset.newThread;
        await API.post(`/courses/${cid}/forum/threads`, { title: $("thread-title").value, body: $("thread-body").value });
        toast("Thread posted"); return navigate("forum", { courseId: cid });
      }
      if (el.dataset.reply) {
        const cid = el.dataset.course, tid = el.dataset.reply;
        await API.post(`/courses/${cid}/forum/threads/${tid}/posts`, { body: $(`reply-${tid}`).value });
        toast("Reply posted"); return navigate("forum", { courseId: cid });
      }
      if (el.dataset.moderate) {
        const cid = el.dataset.course;
        await API.post(`/courses/${cid}/forum/posts/${el.dataset.moderate}/moderate`, { hide: el.dataset.hide === "1" });
        toast("Moderated"); return navigate("forum", { courseId: cid });
      }
      if (el.dataset.comment) {
        await API.post(`/projects/${el.dataset.comment}/comments`, { body: $(`comment-${el.dataset.comment}`).value });
        toast("Comment added"); return navigate("projects");
      }
      if (el.dataset.publishProject !== undefined) {
        await API.post("/projects/showcase", {
          title: $("proj-title").value, description: $("proj-desc").value,
          repo_url: $("proj-repo").value || null, tech_stack: $("proj-stack").value || null,
        });
        toast("Project published"); return navigate("projects");
      }
      if (el.dataset.newAnnouncement !== undefined) {
        await API.post("/announcements", {
          title: $("ann-title").value, body: $("ann-body").value,
          category: $("ann-category").value, location: $("ann-location").value || null,
          course_id: $("ann-course").value ? Number($("ann-course").value) : null,
        });
        toast("Announcement posted"); return navigate("announcements");
      }
      if (el.dataset.addRecruiter !== undefined) {
        await API.post("/admin/recruiters", { email: $("rec-email").value, company: $("rec-company").value });
        toast("Recruiter added"); return navigate("admin");
      }
      if (el.dataset.saveProfile !== undefined) {
        const grad = $("pf-grad").value;
        await API.put("/users/me", {
          full_name: $("pf-name").value, bio: $("pf-bio").value, major: $("pf-major").value,
          grad_year: grad ? Number(grad) : null, avatar_url: $("pf-avatar").value || null,
          github_url: $("pf-github").value || null, linkedin_url: $("pf-linkedin").value || null,
        });
        toast("Profile saved"); return navigate("profile");
      }
    } catch (err) { toast(err.message, true); }
  });

  // sidebar / mobile toggles
  $("sidebar-toggle").onclick = () => document.querySelector(".app-shell").classList.toggle("collapsed");
  $("mobile-menu").onclick = () => document.querySelector(".app-shell").classList.toggle("mobile-open");

  // ---------------- BOOT ----------------
  if (API.token() && API.currentUser()) {
    API.get("/users/me").then((u) => { API.setSession(API.token(), u); enterApp(); })
      .catch(() => { API.clearSession(); showAuth(); });
  } else {
    showAuth();
  }
})();
