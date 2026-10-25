/* Learn++ API client */
const API = (() => {
  const TOKEN_KEY = "learnpp_token";
  const USER_KEY = "learnpp_user";

  function token() { return localStorage.getItem(TOKEN_KEY); }
  function setSession(tok, user) {
    localStorage.setItem(TOKEN_KEY, tok);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }
  function currentUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; }
  }

  async function req(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    const t = token();
    if (t) headers["Authorization"] = "Bearer " + t;
    const res = await fetch("/api" + path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    const data = text ? JSON.parse(text) : {};
    if (!res.ok) {
      const err = new Error(data.detail || ("HTTP " + res.status));
      err.status = res.status;
      throw err;
    }
    return data;
  }

  return {
    token, setSession, clearSession, currentUser,
    get: (p) => req("GET", p),
    post: (p, b) => req("POST", p, b),
    put: (p, b) => req("PUT", p, b),

    // auth
    loginVerify: (email, password, role) => req("POST", "/auth/login/verify", { email, password, role }),
    login: (email, password, role) => req("POST", "/auth/login", { email, password, role }),
    login2fa: (email, code) => req("POST", "/auth/login/2fa", { email, code }),
    signup: (payload) => req("POST", "/auth/signup", payload),

    // --- lesson engine ---
    assignmentLessons: (courseId, assignmentId) => req("GET", `/courses/${courseId}/assignments/${assignmentId}/lessons`),
    flow: (lessonId) => req("GET", `/lessons/${lessonId}/flow`),
    flowAdvance: (lessonId, stageKey) => req("POST", `/lessons/${lessonId}/flow/advance`, { stageKey }),
    flowChallenge: (lessonId, stageKey, answer) => req("POST", `/lessons/${lessonId}/flow/challenge`, { stageKey, answer }),
    flowDraft: (lessonId, stageKey, content) => req("POST", `/lessons/${lessonId}/flow/draft`, { stageKey, content }),
    flowComplete: (lessonId) => req("POST", `/lessons/${lessonId}/flow/complete`),

    tutorStart: (lessonId, reset) => req("POST", `/lessons/${lessonId}/tutor/start`, { reset: !!reset }),
    tutorSend: (lessonId, message) => req("POST", `/lessons/${lessonId}/tutor`, { message }),

    compile: (courseId, assignmentId) => req("GET", `/courses/${courseId}/assignments/${assignmentId}/compile`),
    compileConsent: (courseId, assignmentId, contentHash) =>
      req("POST", `/courses/${courseId}/assignments/${assignmentId}/compile/consent`,
        { reviewed: true, consented: true, contentHash }),

    getPreferences: () => req("GET", "/users/me/preferences"),
    setPreferences: (learningStyles, learningNotes) => req("PUT", "/users/me/preferences", { learningStyles, learningNotes }),

    plan: () => req("GET", "/plan"),
    planReflow: () => req("POST", "/plan/reflow"),
    planUnschedule: (lessonId) => req("POST", `/plan/lessons/${lessonId}/unschedule`),
    planReschedule: (lessonId) => req("POST", `/plan/lessons/${lessonId}/reschedule`),
    planClear: () => req("POST", "/plan/clear"),

    // --- portfolio (student-only: AI-built portfolio + project recommendations) ---
    portfolio: () => req("GET", "/portfolio"),
    portfolioSkillsRefresh: () => req("POST", "/portfolio/skills/refresh"),
    portfolioGuide: (count) => req("GET", `/portfolio/guide${count ? `?count=${count}` : ""}`),
    portfolioSaveProject: (project) => req("POST", "/portfolio/projects", { project }),
    portfolioProjectHelp: (project) => req("POST", "/portfolio/projects/help", { project }),
    portfolioSetStatus: (projectId, status) => req("PUT", `/portfolio/projects/${projectId}`, { status }),
  };
})();
