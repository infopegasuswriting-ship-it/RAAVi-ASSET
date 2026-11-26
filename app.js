/* RAAVi — Your Personal Examiner for PST (Frontend SPA) */
const $ = (id) => document.getElementById(id);

const SCREENS = [
  "screen-auth",
  "screen-subjects",
  "screen-chapters",
  "screen-confirm",
  "screen-test",
  "screen-report",
  "screen-reports",
];

const state = {
  user: null,
  devMailPreview: false,
  serverOffsetMs: 0,
  subjects: {},
  chapters: [],
  selectedSubject: null,
  selectedChapter: null,
  activeTest: null,
  selectedChoice: null,
  startNonce: null,
  pendingDestination: loadSavedDestination(),
  pendingVerifyEmail: "",
  pendingResetEmail: "",
  lastRetryFn: null,
  tickerId: null,
  busy: false,
};

function loadSavedDestination() {
  try {
    const raw = sessionStorage.getItem("raavi_pending_dest");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function savePendingDestination(dest) {
  state.pendingDestination = dest;
  try {
    if (dest) sessionStorage.setItem("raavi_pending_dest", JSON.stringify(dest));
    else sessionStorage.removeItem("raavi_pending_dest");
  } catch {}
}

function showScreen(id) {
  for (const s of SCREENS) {
    $(s).hidden = s !== id;
  }
  window.scrollTo({ top: 0, behavior: "instant" });
}

function showBanner(message, { isInfo = false, retryFn = null } = {}) {
  const banner = $("banner");
  $("banner-text").textContent = message;
  banner.classList.toggle("info", isInfo);
  state.lastRetryFn = retryFn;
  $("banner-retry").hidden = !retryFn;
  banner.hidden = false;
}

function clearBanner() {
  $("banner").hidden = true;
  state.lastRetryFn = null;
}

function setLoading(active, text = "Loading…") {
  state.busy = active;
  $("loading-text").textContent = text;
  $("loading-bar").hidden = !active;
}

async function api(path, { method = "GET", body = null, timeoutMs = 20000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const opts = { method, signal: ctrl.signal, headers: {} };
    if (body !== null) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(path, opts);
    let data = {};
    try {
      data = await resp.json();
    } catch {
      data = {};
    }
    if (!resp.ok) {
      const err = new Error(data.error || `Request failed (${resp.status}).`);
      err.status = resp.status;
      err.code = data.code || "error";
      throw err;
    }
    return data;
  } catch (err) {
    if (err.name === "AbortError" || err instanceof TypeError) {
      const netErr = new Error(
        "Unable to reach the RAAVi server. Check your connection or ensure RAAVi is running, then retry."
      );
      netErr.isNetwork = true;
      throw netErr;
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function runAction(fn, { loadingText = "Please wait…", retryable = true } = {}) {
  return async (ev) => {
    if (ev) ev.preventDefault();
    if (state.busy) return;
    clearBanner();
    setLoading(true, loadingText);
    try {
      await fn();
    } catch (err) {
      showBanner(err.message || "Something went wrong.", {
        retryFn: retryable ? () => runAction(fn, { loadingText, retryable })() : null,
      });
    } finally {
      setLoading(false);
    }
  };
}

function serverNowSec() {
  return (Date.now() + state.serverOffsetMs) / 1000;
}

function formatDurationHM(totalSeconds) {
  const mins = Math.max(1, Math.ceil(totalSeconds / 60));
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${String(h).padStart(2, "0")}h ${String(m).padStart(2, "0")}m`;
}

function formatDate(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function updateTopbar() {
  const u = state.user;
  $("nav-auth").hidden = !!u;
  $("nav-logout").hidden = !u;
  $("nav-reports").hidden = !(u && u.verified);
  $("btn-view-all-reports").hidden = !(u && u.verified);
  if (u) {
    $("user-pill").textContent = u.verified ? u.email : `${u.email} (unverified)`;
    $("user-pill").hidden = false;
  } else {
    $("user-pill").hidden = true;
  }
  $("unverified-callout").hidden = !(u && !u.verified);
}

/* ── Live Cooldown Ticker ── */
function stopTicker() {
  if (state.tickerId) {
    clearInterval(state.tickerId);
    state.tickerId = null;
  }
}

function computeRemainingSeconds(subjInfo) {
  if (!subjInfo || !subjInfo.next_available_at) return 0;
  return Math.max(0, Math.ceil(subjInfo.next_available_at - serverNowSec()));
}

function refreshTickerDisplays() {
  let anyActive = false;
  let expiredNow = false;
  for (const subj of ["History", "Geography"]) {
    const info = state.subjects[subj];
    if (!info) continue;
    const rem = computeRemainingSeconds(info);
    const el = document.querySelector(`[data-cooldown-for="${subj}"]`);
    if (rem > 0) {
      anyActive = true;
      const text = `Limit reached. ${formatDurationHM(rem)} remaining until your next ${subj} test.`;
      if (el) el.textContent = text;
      if (state.selectedSubject === subj && !$("screen-chapters").hidden) {
        $("chapters-status-banner").textContent = text;
        $("chapters-status-banner").className = "callout callout-warn";
        $("chapters-status-banner").hidden = false;
      }
      if (state.selectedSubject === subj && !$("screen-confirm").hidden && !info.active_session) {
        $("confirm-blocker").textContent = text;
        $("confirm-blocker").hidden = false;
        $("btn-start-test").disabled = true;
      }
    } else if (info.next_available_at) {
      // Cooldown just reached zero!
      info.next_available_at = null;
      info.cooldown_seconds = 0;
      expiredNow = true;
    }
  }
  if (expiredNow) {
    stopTicker();
    loadSubjects({ render: !$("screen-subjects").hidden }).catch(() => {});
    if (state.selectedSubject && !$("screen-confirm").hidden) {
      renderConfirmScreen();
    }
  } else if (!anyActive) {
    stopTicker();
  }
}

function startTickerIfNeeded() {
  stopTicker();
  const hasCooldown = ["History", "Geography"].some((s) => computeRemainingSeconds(state.subjects[s]) > 0);
  if (hasCooldown) {
    state.tickerId = setInterval(refreshTickerDisplays, 1000);
  }
}

/* ── Auth Screen ── */
function setAuthTab(tab) {
  const isLogin = tab === "login";
  $("tab-login").classList.toggle("active", isLogin);
  $("tab-register").classList.toggle("active", !isLogin);
  $("tab-login").setAttribute("aria-selected", String(isLogin));
  $("tab-register").setAttribute("aria-selected", String(!isLogin));
  $("form-login").hidden = !isLogin;
  $("form-register").hidden = isLogin;
  $("form-verify").hidden = true;
  $("form-forgot").hidden = true;
  $("form-reset").hidden = true;
  $("auth-tabs").hidden = false;
  $("auth-heading").textContent = isLogin ? "Sign in to RAAVi" : "Create your RAAVi account";
}

function openAuthScreen(mode = "login", email = "") {
  showScreen("screen-auth");
  const dest = state.pendingDestination;
  if (dest && dest.subject) {
    $("auth-destination-note").textContent = dest.chapter
      ? `Sign in or verify your email to continue to ${dest.subject} · ${dest.chapter}.`
      : `Sign in or verify your email to continue to ${dest.subject}.`;
    $("auth-destination-note").hidden = false;
  } else {
    $("auth-destination-note").hidden = true;
  }

  if (mode === "verify") {
    $("auth-tabs").hidden = true;
    $("form-login").hidden = true;
    $("form-register").hidden = true;
    $("form-forgot").hidden = true;
    $("form-reset").hidden = true;
    $("form-verify").hidden = false;
    state.pendingVerifyEmail = email || state.user?.email || "";
    $("verify-email-display").textContent = state.pendingVerifyEmail;
    $("auth-heading").textContent = "Verify your email";
  } else {
    setAuthTab(mode === "register" ? "register" : "login");
    if (email) {
      $("login-email").value = email;
      $("reg-email").value = email;
    }
  }
}

async function continueAfterAuth() {
  updateTopbar();
  const dest = state.pendingDestination;
  if (dest && dest.subject && dest.chapter) {
    savePendingDestination(null);
    await openChapters(dest.subject);
    openConfirm(dest.subject, dest.chapter);
    return;
  }
  if (dest && dest.subject) {
    savePendingDestination(null);
    await openChapters(dest.subject);
    return;
  }
  await openSubjects();
}

/* ── Subjects Screen ── */
async function loadSubjects({ render = true } = {}) {
  const data = await api("/api/subjects");
  if (data.server_now) {
    state.serverOffsetMs = data.server_now * 1000 - Date.now();
  }
  state.subjects = data.subjects;
  if (render) renderSubjects();
  startTickerIfNeeded();
}

function renderSubjects() {
  const container = $("subject-cards");
  container.replaceChildren();

  const configs = [
    {
      name: "History",
      subtitle: "16 chapters · Mughal decline to International relations",
    },
    {
      name: "Geography",
      subtitle: "12 chapters · Topography to Population and employment",
    },
  ];

  for (const cfg of configs) {
    const info = state.subjects[cfg.name] || { available: true, cooldown_seconds: 0, active_session: null };
    const card = document.createElement("div");
    card.className = "subject-card";

    const h2 = document.createElement("h2");
    h2.textContent = cfg.name;
    const sub = document.createElement("p");
    sub.className = "subject-meta";
    sub.textContent = cfg.subtitle;

    const pill = document.createElement("span");
    const rem = computeRemainingSeconds(info);
    if (info.active_session) {
      pill.className = "status-pill status-resume";
      pill.textContent = `Unfinished test: ${info.active_session.chapter} (Question ${info.active_session.current_index + 1} of ${info.active_session.total})`;
    } else if (rem > 0) {
      pill.className = "status-pill status-cooldown";
      pill.setAttribute("data-cooldown-for", cfg.name);
      pill.textContent = `Limit reached. ${formatDurationHM(rem)} remaining until your next ${cfg.name} test.`;
    } else {
      pill.className = "status-pill status-available";
      pill.textContent = "Available · 10-question chapter test";
    }

    card.append(h2, sub, pill);

    if (info.active_session && rem > 0) {
      const cdLine = document.createElement("p");
      cdLine.className = "subject-meta";
      cdLine.setAttribute("data-cooldown-for", cfg.name);
      cdLine.textContent = `Limit reached. ${formatDurationHM(rem)} remaining until your next ${cfg.name} test.`;
      card.append(cdLine);
    }

    const actions = document.createElement("div");
    actions.className = "subject-actions";

    if (info.active_session) {
      const btnResume = document.createElement("button");
      btnResume.type = "button";
      btnResume.className = "btn-primary";
      btnResume.textContent = "Resume test";
      btnResume.onclick = runAction(() => resumeSession(info.active_session.id), { loadingText: "Resuming test…" });
      actions.append(btnResume);

      if (info.unfinished_blocking_new) {
        const btnEnd = document.createElement("button");
        btnEnd.type = "button";
        btnEnd.className = "btn-secondary";
        btnEnd.textContent = "End unfinished test";
        btnEnd.onclick = runAction(async () => {
          if (!confirm(`End your unfinished ${cfg.name} test in "${info.active_session.chapter}" as incomplete? Incomplete attempts are excluded from completed-score trends.`)) return;
          const res = await api(`/api/test/${info.active_session.id}/end-incomplete`, { method: "POST", body: {} });
          await loadSubjects({ render: false });
          renderReport(res.report);
        }, { loadingText: "Closing unfinished test…" });
        actions.append(btnEnd);
      }
    }

    const btnBrowse = document.createElement("button");
    btnBrowse.type = "button";
    btnBrowse.className = info.active_session ? "btn-secondary" : "btn-primary";
    btnBrowse.textContent = `Choose ${cfg.name} chapter`;
    btnBrowse.onclick = runAction(() => openChapters(cfg.name), { loadingText: `Loading ${cfg.name} chapters…` });
    actions.append(btnBrowse);

    card.append(actions);
    container.append(card);
  }
}

async function openSubjects() {
  showScreen("screen-subjects");
  await loadSubjects({ render: true });
}

/* ── Chapters Screen ── */
async function openChapters(subject) {
  state.selectedSubject = subject;
  const data = await api(`/api/chapters/${encodeURIComponent(subject)}`);
  if (data.server_now) {
    state.serverOffsetMs = data.server_now * 1000 - Date.now();
  }
  state.subjects[subject] = data.availability;
  state.chapters = data.chapters;

  $("chapters-eyebrow").textContent = subject.toUpperCase();
  $("chapters-title").textContent = `${subject} chapters (${data.chapters.length})`;

  const banner = $("chapters-status-banner");
  const rem = computeRemainingSeconds(data.availability);
  if (data.availability.active_session) {
    const act = data.availability.active_session;
    banner.textContent = `You have an unfinished ${subject} test in "${act.chapter}" (Question ${act.current_index + 1} of ${act.total}).`;
    banner.className = "callout";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-small";
    btn.textContent = "Resume test";
    btn.onclick = runAction(() => resumeSession(act.id), { loadingText: "Resuming test…" });
    banner.append(btn);
    banner.hidden = false;
  } else if (rem > 0) {
    banner.textContent = `Limit reached. ${formatDurationHM(rem)} remaining until your next ${subject} test.`;
    banner.className = "callout callout-warn";
    banner.hidden = false;
  } else {
    banner.hidden = true;
  }

  const grid = $("chapter-grid");
  grid.replaceChildren();
  for (const ch of data.chapters) {
    const card = document.createElement("div");
    card.className = "chapter-card";

    const num = document.createElement("span");
    num.className = "chapter-num";
    num.textContent = `Chapter ${ch.number}`;

    const title = document.createElement("div");
    title.className = "chapter-title";
    title.textContent = ch.chapter;

    const stats = document.createElement("div");
    stats.className = "chapter-stats";
    if (ch.completed_attempts > 0) {
      stats.textContent = `Latest: ${ch.latest_score}/${ch.latest_total} · ${ch.completed_attempts} completed attempt${ch.completed_attempts === 1 ? "" : "s"}`;
    } else {
      stats.textContent = "No attempts yet";
    }

    const actions = document.createElement("div");
    actions.className = "chapter-actions";

    if (ch.active_session) {
      const btnRes = document.createElement("button");
      btnRes.type = "button";
      btnRes.className = "btn-primary btn-small";
      btnRes.textContent = "Resume test";
      btnRes.onclick = runAction(() => resumeSession(ch.active_session.id), { loadingText: "Resuming test…" });
      actions.append(btnRes);
    } else {
      const btnSel = document.createElement("button");
      btnSel.type = "button";
      btnSel.className = "btn-secondary btn-small";
      btnSel.textContent = "Select chapter";
      btnSel.onclick = () => openConfirm(subject, ch.chapter);
      actions.append(btnSel);
    }

    if (ch.latest_report_id) {
      const btnRep = document.createElement("button");
      btnRep.type = "button";
      btnRep.className = "btn-link";
      btnRep.textContent = "Latest report";
      btnRep.onclick = runAction(() => loadAndRenderReport(ch.latest_report_id), { loadingText: "Loading report…" });
      actions.append(btnRep);
    }

    card.append(num, title, stats, actions);
    grid.append(card);
  }

  showScreen("screen-chapters");
  startTickerIfNeeded();
}

/* ── Confirm Screen ── */
function openConfirm(subject, chapter) {
  state.selectedSubject = subject;
  state.selectedChapter = chapter;
  state.startNonce = null;
  renderConfirmScreen();
  showScreen("screen-confirm");
}

function renderConfirmScreen() {
  const subject = state.selectedSubject;
  const chapter = state.selectedChapter;
  $("confirm-subject").textContent = subject.toUpperCase();
  $("confirm-chapter").textContent = chapter;
  $("confirm-subj-inline").textContent = subject;

  const info = state.subjects[subject] || { available: true, cooldown_seconds: 0, active_session: null };
  const rem = computeRemainingSeconds(info);
  const blocker = $("confirm-blocker");
  const startBtn = $("btn-start-test");

  // Clean up any dynamic resume/end buttons from previous renders
  for (const old of $("confirm-actions").querySelectorAll("[data-dynamic='1']")) {
    old.remove();
  }

  if (!state.user || !state.user.verified) {
    blocker.textContent = state.user
      ? "Verify your email address before starting this test. Your selected chapter will be kept."
      : "Sign in or create a verified student account to start this test. Your selected chapter will be kept.";
    blocker.hidden = false;
    startBtn.hidden = false;
    startBtn.disabled = false;
    startBtn.textContent = state.user ? "Verify email & start test" : "Sign in to start test";
    return;
  }

  startBtn.textContent = "Start test";

  if (info.active_session) {
    const act = info.active_session;
    blocker.textContent = `You have an unfinished ${subject} test in "${act.chapter}" (Question ${act.current_index + 1} of ${act.total}).`;
    blocker.hidden = false;
    startBtn.hidden = true;

    const btnRes = document.createElement("button");
    btnRes.type = "button";
    btnRes.className = "btn-primary btn-lg";
    btnRes.setAttribute("data-dynamic", "1");
    btnRes.textContent = `Resume ${act.chapter}`;
    btnRes.onclick = runAction(() => resumeSession(act.id), { loadingText: "Resuming test…" });
    $("confirm-actions").prepend(btnRes);

    if (info.unfinished_blocking_new) {
      const btnEnd = document.createElement("button");
      btnEnd.type = "button";
      btnEnd.className = "btn-secondary";
      btnEnd.setAttribute("data-dynamic", "1");
      btnEnd.textContent = "End unfinished test first";
      btnEnd.onclick = runAction(async () => {
        if (!confirm(`End "${act.chapter}" as incomplete? You can then start "${chapter}".`)) return;
        await api(`/api/test/${act.id}/end-incomplete`, { method: "POST", body: {} });
        await loadSubjects({ render: false });
        renderConfirmScreen();
      }, { loadingText: "Closing unfinished test…" });
      $("confirm-actions").append(btnEnd);
    }
    return;
  }

  if (rem > 0) {
    blocker.textContent = `Limit reached. ${formatDurationHM(rem)} remaining until your next ${subject} test.`;
    blocker.hidden = false;
    startBtn.hidden = false;
    startBtn.disabled = true;
    return;
  }

  blocker.hidden = true;
  startBtn.hidden = false;
  startBtn.disabled = false;
}

async function handleStartTest() {
  if (!state.user) {
    savePendingDestination({ subject: state.selectedSubject, chapter: state.selectedChapter });
    openAuthScreen("login");
    return;
  }
  if (!state.user.verified) {
    savePendingDestination({ subject: state.selectedSubject, chapter: state.selectedChapter });
    const res = await api("/api/auth/resend", { method: "POST", body: { email: state.user.email } }).catch(() => ({}));
    openAuthScreen("verify", state.user.email);
    if (res.dev_code) {
      $("dev-mail-hint").textContent = `Local development verification code: ${res.dev_code}`;
      $("dev-mail-hint").hidden = false;
    }
    return;
  }

  state.startNonce ??= crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  const res = await api("/api/start-test", {
    method: "POST",
    body: {
      subject: state.selectedSubject,
      chapter: state.selectedChapter,
      nonce: state.startNonce,
    },
  });
  state.startNonce = null;
  await resumeSession(res.session_id);
}

/* ── Active Test Screen ── */
async function resumeSession(sessionId) {
  const data = await api(`/api/test/${sessionId}`);
  if (data.status !== "active" && data.report) {
    renderReport(data.report);
    return;
  }
  state.activeTest = data;
  state.selectedChoice = null;
  renderActiveQuestion();
  showScreen("screen-test");
}

function renderActiveQuestion() {
  const test = state.activeTest;
  const q = test.current_question;
  state.selectedChoice = null;

  $("test-subject-chapter").textContent = `${test.subject} · ${test.chapter}`;
  $("test-progress-label").textContent = `Question ${q.number} of ${q.total}`;
  $("test-progress-bar").style.width = `${(q.number / q.total) * 100}%`;
  $("question-meta").textContent = `${q.subtopic} · ${q.skill}`;
  $("question-stem").textContent = q.stem;

  // Map figure handling
  const fig = $("question-figure");
  if (q.map_asset) {
    const img = $("question-map-img");
    img.src = `/assets/${q.map_asset}`;
    img.alt = q.map_info?.alt || `Reference map for ${q.subtopic}`;
    img.onerror = () => {
      fig.hidden = true;
      showBanner("Map asset failed to load. Check your connection and retry.", {
        retryFn: () => resumeSession(test.id),
      });
    };
    $("question-map-caption").textContent = q.map_info?.title || "Reference map";
    $("modal-map-img").src = img.src;
    $("modal-map-img").alt = img.alt;
    $("modal-map-caption").textContent = $("question-map-caption").textContent;
    fig.hidden = false;
  } else {
    fig.hidden = true;
  }

  const choicesWrap = $("question-choices");
  choicesWrap.replaceChildren();
  const shortWrap = $("short-answer-wrap");

  if (q.question_type === "short_answer") {
    choicesWrap.hidden = true;
    shortWrap.hidden = false;
    $("short-answer-input").value = "";
    $("btn-submit-answer").disabled = true;
  } else {
    shortWrap.hidden = true;
    choicesWrap.hidden = false;
    const letters = ["A", "B", "C", "D"];
    q.choices.forEach((choice, idx) => {
      const label = document.createElement("label");
      label.className = "choice-option";

      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "raavi_choice";
      radio.value = choice;
      radio.onchange = () => {
        state.selectedChoice = choice;
        for (const el of choicesWrap.querySelectorAll(".choice-option")) {
          el.classList.remove("selected");
        }
        label.classList.add("selected");
        $("btn-submit-answer").disabled = false;
      };

      const letterSpan = document.createElement("span");
      letterSpan.className = "choice-letter";
      letterSpan.textContent = `${letters[idx]}.`;

      const textSpan = document.createElement("span");
      textSpan.textContent = choice;

      label.append(radio, letterSpan, textSpan);
      choicesWrap.append(label);
    });
    $("btn-submit-answer").disabled = true;
  }

  $("test-controls").hidden = false;
  $("feedback-card").hidden = true;
}

async function submitCurrentAnswer(skip) {
  const test = state.activeTest;
  const q = test.current_question;
  const response = skip
    ? null
    : q.question_type === "short_answer"
      ? $("short-answer-input").value
      : state.selectedChoice;

  if (!skip && (!response || !String(response).trim())) {
    showBanner("Please select an answer option or choose Skip.");
    return;
  }

  const res = await api(`/api/test/${test.id}/answer`, {
    method: "POST",
    body: {
      question_index: q.index,
      response,
      skip,
    },
  });

  if (res.completed && res.report) {
    await loadSubjects({ render: false }).catch(() => {});
    renderReport(res.report);
    return;
  }

  // Show immediate feedback before advancing to next question
  const card = $("feedback-card");
  card.className = "feedback-card " + (res.is_correct ? "is-correct" : res.is_skip ? "is-skipped" : "is-incorrect");
  $("feedback-badge").textContent = res.is_correct ? "✓ Correct (1 mark)" : res.is_skip ? "— Skipped (0 marks)" : "✗ Incorrect (0 marks)";
  $("feedback-your-answer").textContent = res.is_skip
    ? "Your answer: Skipped"
    : `Your answer: ${res.student_response}`;
  $("feedback-correct-answer").textContent = `Correct answer: ${res.correct_answer}`;
  $("feedback-explanation").textContent = res.explanation;
  $("feedback-refs").textContent = `Source reference: ${res.refs}`;

  $("test-controls").hidden = true;
  $("btn-next-question").textContent = q.number >= q.total ? "View report →" : `Continue to Question ${q.number + 1} →`;
  card.hidden = false;

  // Disable radio/input edits after final submission
  for (const inp of $("question-choices").querySelectorAll("input")) {
    inp.disabled = true;
  }
  $("short-answer-input").disabled = true;
}

/* ── Report Screen ── */
async function loadAndRenderReport(reportOrSessionId) {
  const data = await api(`/api/reports/${reportOrSessionId}`);
  renderReport(data.report);
}

function renderReport(report) {
  state.selectedSubject = report.subject;
  state.selectedChapter = report.chapter;
  $("report-eyebrow").textContent = report.status === "incomplete" ? "INCOMPLETE ATTEMPT REPORT" : "SAVED CHAPTER REPORT";
  const statusSuffix = report.status === "incomplete" ? " (Incomplete)" : "";
  $("report-title").textContent = `${report.subject} · ${report.chapter} · ${report.score}/${report.total}${statusSuffix}`;

  const strip = $("report-summary-strip");
  strip.replaceChildren();
  const badge = document.createElement("div");
  badge.className = "score-badge";
  badge.textContent = `${report.score}/${report.total}`;

  const info = document.createElement("div");
  const p1 = document.createElement("div");
  p1.innerHTML = `<strong>${report.subject}</strong> · ${report.chapter}`;
  const p2 = document.createElement("div");
  p2.className = "help-text";
  p2.textContent = `Completed ${formatDate(report.completed_at)} · ${
    report.status === "incomplete" ? "Ended incomplete (excluded from completed-score trends)" : "Completed attempt"
  }`;
  info.append(p1, p2);
  strip.append(badge, info);

  const trend = $("report-trend-box");
  trend.replaceChildren();
  if (report.status === "incomplete") {
    trend.textContent = "This incomplete attempt is preserved in your history and excluded from completed-score trends for this chapter.";
  } else if (report.is_first_attempt) {
    trend.textContent = "First attempt in this chapter. Complete another test in this same chapter later to see your progress change.";
  } else {
    const prev = report.previous_comparable;
    const diff = report.delta;
    const diffStr = diff > 0 ? `+${diff}` : diff < 0 ? `${diff}` : "0";
    const seriesStr = report.comparable_history.map((h) => `${h.score}/${h.total}`).join(" → ");
    trend.innerHTML = `<strong>Comparable chapter progress (${report.chapter}):</strong> Latest <strong>${report.score}/${report.total}</strong> · Previous <strong>${prev.score}/${prev.total}</strong> (change: <strong>${diffStr}</strong>)<br><span class="help-text">Completed series: ${seriesStr}</span>`;
  }

  const list = $("report-outcomes");
  list.replaceChildren();
  for (const out of report.outcomes) {
    const cls = out.is_correct ? "correct" : out.is_skip ? "skipped" : "incorrect";
    const symbol = out.is_correct ? "✓ Correct" : out.is_skip ? "— Skipped" : "✗ Incorrect";

    const item = document.createElement("div");
    item.className = `outcome-item ${cls}`;

    const head = document.createElement("div");
    head.className = "outcome-head";
    const qnum = document.createElement("span");
    qnum.textContent = `Question ${out.number} (${out.subtopic})`;
    const st = document.createElement("span");
    st.className = `outcome-status ${cls}`;
    st.textContent = `${symbol} · ${out.marks}/1`;
    head.append(qnum, st);

    const stem = document.createElement("div");
    stem.className = "outcome-stem";
    stem.textContent = out.stem;

    const resp = document.createElement("div");
    resp.className = "outcome-detail";
    resp.textContent = out.is_skip ? "Your response: Skipped" : `Your response: ${out.student_response}`;

    const corr = document.createElement("div");
    corr.className = "outcome-detail";
    corr.innerHTML = `<strong>Correct answer:</strong> `;
    corr.append(document.createTextNode(out.correct_answer));

    const exp = document.createElement("div");
    exp.className = "outcome-detail";
    exp.textContent = out.explanation;

    const src = document.createElement("div");
    src.className = "source-ref";
    src.textContent = `Source: ${out.refs}`;

    item.append(head, stem, resp, corr, exp, src);
    list.append(item);
  }

  showScreen("screen-report");
}

/* ── Report History Screen ── */
async function openReportHistory() {
  const data = await api("/api/reports");
  const container = $("reports-list");
  container.replaceChildren();

  if (!data.reports.length) {
    const p = document.createElement("p");
    p.className = "help-text";
    p.textContent = "You have no saved reports yet. Choose History or Geography to begin.";
    container.append(p);
    showScreen("screen-reports");
    return;
  }

  for (const subj of ["History", "Geography"]) {
    const rows = data.reports.filter((r) => r.subject === subj);
    const group = document.createElement("div");
    group.className = "history-group";
    const h2 = document.createElement("h2");
    h2.textContent = `${subj} (${rows.length})`;
    group.append(h2);

    if (!rows.length) {
      const empty = document.createElement("p");
      empty.className = "help-text";
      empty.textContent = `No ${subj} attempts yet.`;
      group.append(empty);
    } else {
      for (const r of rows) {
        const row = document.createElement("div");
        row.className = "history-row";

        const left = document.createElement("div");
        left.innerHTML = `<strong>${r.chapter}</strong> · ${r.score}/${r.total} ${
          r.status === "incomplete" ? '<span class="status-pill status-cooldown">Incomplete</span>' : ""
        }<div class="help-text">${formatDate(r.completed_at)}</div>`;

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn-secondary btn-small";
        btn.textContent = "Open report";
        btn.onclick = runAction(() => loadAndRenderReport(r.id), { loadingText: "Loading report…" });

        row.append(left, btn);
        group.append(row);
      }
    }
    container.append(group);
  }

  showScreen("screen-reports");
}

/* ── Event Bindings ── */
$("banner-dismiss").onclick = clearBanner;
$("banner-retry").onclick = () => {
  if (state.lastRetryFn) state.lastRetryFn();
};

$("nav-home").onclick = runAction(openSubjects);
$("nav-subjects").onclick = runAction(openSubjects);
$("nav-reports").onclick = runAction(openReportHistory);
$("btn-view-all-reports").onclick = runAction(openReportHistory);
$("nav-auth").onclick = () => openAuthScreen("login");
$("nav-logout").onclick = runAction(async () => {
  await api("/api/auth/logout", { method: "POST", body: {} });
  state.user = null;
  state.subjects = {};
  state.activeTest = null;
  savePendingDestination(null);
  updateTopbar();
  openAuthScreen("login");
  showBanner("You have signed out.", { isInfo: true });
}, { retryable: false });

$("btn-go-verify").onclick = runAction(async () => {
  if (!state.user) return;
  const res = await api("/api/auth/resend", { method: "POST", body: { email: state.user.email } }).catch(() => ({}));
  openAuthScreen("verify", state.user.email);
  if (res.dev_code) {
    $("dev-mail-hint").textContent = `Local development verification code: ${res.dev_code}`;
    $("dev-mail-hint").hidden = false;
  }
});

$("tab-login").onclick = () => setAuthTab("login");
$("tab-register").onclick = () => setAuthTab("register");

$("btn-show-forgot").onclick = () => {
  $("auth-tabs").hidden = true;
  $("form-login").hidden = true;
  $("form-register").hidden = true;
  $("form-verify").hidden = true;
  $("form-reset").hidden = true;
  $("form-forgot").hidden = false;
  $("forgot-email").value = $("login-email").value;
  $("auth-heading").textContent = "Reset your password";
};
$("btn-forgot-back").onclick = () => setAuthTab("login");
$("btn-reset-back").onclick = () => setAuthTab("login");
$("btn-verify-back").onclick = () => setAuthTab("login");

$("form-login").onsubmit = runAction(async () => {
  const res = await api("/api/auth/login", {
    method: "POST",
    body: { email: $("login-email").value, password: $("login-password").value },
  });
  state.user = res.user;
  updateTopbar();
  if (!state.user.verified) {
    const r = await api("/api/auth/resend", { method: "POST", body: { email: state.user.email } }).catch(() => ({}));
    openAuthScreen("verify", state.user.email);
    if (r.dev_code) {
      $("dev-mail-hint").textContent = `Local development verification code: ${r.dev_code}`;
      $("dev-mail-hint").hidden = false;
    }
    return;
  }
  await continueAfterAuth();
}, { loadingText: "Signing in…" });

$("form-register").onsubmit = runAction(async () => {
  const res = await api("/api/auth/register", {
    method: "POST",
    body: { email: $("reg-email").value, password: $("reg-password").value },
  });
  state.user = res.user;
  updateTopbar();
  openAuthScreen("verify", res.user.email);
  if (res.dev_code) {
    $("dev-mail-hint").textContent = `Local development verification code: ${res.dev_code}`;
    $("dev-mail-hint").hidden = false;
  } else {
    $("dev-mail-hint").hidden = true;
  }
}, { loadingText: "Creating account…" });

$("form-verify").onsubmit = runAction(async () => {
  const res = await api("/api/auth/verify", {
    method: "POST",
    body: { email: state.pendingVerifyEmail, code: $("verify-code").value },
  });
  state.user = res.user;
  $("verify-code").value = "";
  await continueAfterAuth();
}, { loadingText: "Verifying email…" });

$("btn-resend-code").onclick = runAction(async () => {
  const res = await api("/api/auth/resend", {
    method: "POST",
    body: { email: state.pendingVerifyEmail },
  });
  if (res.dev_code) {
    $("dev-mail-hint").textContent = `Local development verification code: ${res.dev_code}`;
    $("dev-mail-hint").hidden = false;
  }
  showBanner("A new verification code has been sent.", { isInfo: true });
}, { loadingText: "Sending verification code…" });

$("form-forgot").onsubmit = runAction(async () => {
  const email = $("forgot-email").value.trim();
  const res = await api("/api/auth/forgot-password", { method: "POST", body: { email } });
  state.pendingResetEmail = email;
  $("reset-email-display").textContent = email;
  $("form-forgot").hidden = true;
  $("form-reset").hidden = false;
  if (res.dev_code) {
    $("dev-reset-hint").textContent = `Local development reset code: ${res.dev_code}`;
    $("dev-reset-hint").hidden = false;
  } else {
    $("dev-reset-hint").hidden = true;
  }
}, { loadingText: "Sending reset code…" });

$("form-reset").onsubmit = runAction(async () => {
  const res = await api("/api/auth/reset-password", {
    method: "POST",
    body: {
      email: state.pendingResetEmail,
      code: $("reset-code").value,
      password: $("reset-password").value,
    },
  });
  state.user = res.user;
  $("reset-code").value = "";
  $("reset-password").value = "";
  showBanner("Password updated and signed in.", { isInfo: true });
  await continueAfterAuth();
}, { loadingText: "Updating password…" });

$("btn-chapters-back").onclick = runAction(openSubjects);
$("btn-confirm-back").onclick = runAction(() => openChapters(state.selectedSubject));
$("btn-confirm-other").onclick = runAction(() => openChapters(state.selectedSubject));
$("btn-start-test").onclick = runAction(handleStartTest, { loadingText: "Assembling 10 questions…" });

$("short-answer-input").oninput = () => {
  $("btn-submit-answer").disabled = !$("short-answer-input").value.trim();
};

$("btn-submit-answer").onclick = runAction(() => submitCurrentAnswer(false), { loadingText: "Checking answer…" });
$("btn-skip-answer").onclick = runAction(() => submitCurrentAnswer(true), { loadingText: "Recording skip…" });
$("btn-next-question").onclick = runAction(() => resumeSession(state.activeTest.id), { loadingText: "Loading next question…" });
$("btn-pause-exit").onclick = runAction(async () => {
  state.activeTest = null;
  await openSubjects();
});

$("btn-report-chapters").onclick = runAction(() => openChapters(state.selectedSubject));
$("btn-report-subjects").onclick = runAction(openSubjects);
$("btn-report-all").onclick = runAction(openReportHistory);
$("btn-reports-back").onclick = runAction(openSubjects);

$("btn-zoom-map").onclick = () => { $("map-modal").hidden = false; };
$("btn-close-map").onclick = () => { $("map-modal").hidden = true; };
$("map-modal").onclick = (e) => {
  if (e.target === $("map-modal")) $("map-modal").hidden = true;
};

/* Keyboard support during active test */
document.addEventListener("keydown", (e) => {
  if ($("screen-test").hidden || state.busy) return;
  if (!$("feedback-card").hidden) {
    if (e.key === "Enter") {
      e.preventDefault();
      $("btn-next-question").click();
    }
    return;
  }
  const radios = [...$("question-choices").querySelectorAll('input[type="radio"]')];
  if (!radios.length) return;
  const idxMap = { "1": 0, "2": 1, "3": 2, "4": 3, a: 0, b: 1, c: 2, d: 3 };
  const mapped = idxMap[e.key.toLowerCase()];
  if (mapped !== undefined && radios[mapped] && !radios[mapped].disabled) {
    radios[mapped].checked = true;
    radios[mapped].dispatchEvent(new Event("change"));
  }
});

/* ── App Boot ── */
(async function boot() {
  setLoading(true, "Starting RAAVi…");
  try {
    const params = new URLSearchParams(window.location.search);
    const verifyToken = params.get("verify_token");
    const verifyEmail = params.get("email");
    if (verifyToken && verifyEmail) {
      const vres = await api("/api/auth/verify", {
        method: "POST",
        body: { email: verifyEmail, token: verifyToken },
      });
      state.user = vres.user;
      window.history.replaceState({}, "", "/");
      updateTopbar();
      showBanner("Email verified! Continuing to your destination.", { isInfo: true });
      await continueAfterAuth();
      return;
    }

    const me = await api("/api/me");
    state.user = me.user;
    state.devMailPreview = !!me.dev_mail_preview;
    if (me.server_now) {
      state.serverOffsetMs = me.server_now * 1000 - Date.now();
    }
    updateTopbar();

    if (state.user && state.user.verified) {
      await continueAfterAuth();
    } else if (state.user && !state.user.verified) {
      openAuthScreen("verify", state.user.email);
    } else {
      await openSubjects();
    }
  } catch (err) {
    showBanner(err.message || "Could not initialize RAAVi.", {
      retryFn: () => window.location.reload(),
    });
  } finally {
    setLoading(false);
  }
})();
