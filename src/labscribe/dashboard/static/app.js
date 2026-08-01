// LabScribe dashboard logic — plain JS, no framework.
// Talks to the local FastAPI server over /api/*.

// ---------- small helpers ----------
const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = "HTTP " + res.status;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function postJSON(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ---------- view switching ----------
const navButtons = document.querySelectorAll(".nav-btn");
navButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    navButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
    $("view-" + btn.dataset.view).classList.remove("hidden");
    if (btn.dataset.view === "agents") loadAgents();
  });
});

// ---------- status polling ----------
// The server rescans the capture folder on every request (see orchestrator.py
// for why polling beats file watchers on VirtualBox shares).
let activeStartedAt = null;

function fmtElapsed(startStr) {
  // startStr is "YYYY-MM-DD HH:MM:SS" local time
  const start = new Date(startStr.replace(" ", "T"));
  let secs = Math.max(0, Math.floor((Date.now() - start.getTime()) / 1000));
  const h = Math.floor(secs / 3600); secs %= 3600;
  const m = Math.floor(secs / 60);  secs %= 60;
  return (h ? h + "h " : "") + m + "m " + String(secs).padStart(2, "0") + "s";
}

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    const active = s.active;
    activeStartedAt = active ? active.started_at : null;

    $("stat-capture").textContent = active ? "On" : "Off";
    $("stat-capture").classList.toggle("live", !!active);
    $("stat-session").textContent = active ? active.name : "—";
    $("stat-transcripts").textContent = s.counts.transcripts;
    $("stat-screenshots").textContent = s.counts.screenshots;
    $("stat-notes").textContent = s.counts.notes;
    $("stat-generated").textContent = s.last_generated || "never";

    $("btn-start").disabled = !!active;
    $("btn-stop").disabled = !active;
    $("rec-indicator").classList.toggle("hidden", !active);

    if (!s.configured) {
      $("config-hint").textContent =
        "Not configured yet — open Settings to set your capture folder and repo path.";
    } else if (!s.shared_folder_ok) {
      $("config-hint").textContent =
        "Shared capture folder is unreachable — check the path in Settings.";
    } else {
      $("config-hint").textContent = "";
    }
  } catch (_) {
    /* server briefly unavailable; next poll will catch up */
  }
}

// Elapsed ticks every second locally; folder rescan every 3s
setInterval(() => {
  $("stat-elapsed").textContent = activeStartedAt ? fmtElapsed(activeStartedAt) : "—";
}, 1000);
setInterval(refreshStatus, 3000);

// ---------- session controls ----------
const actionError = $("action-error");

$("btn-start").addEventListener("click", async () => {
  actionError.textContent = "";
  const name = prompt(
    "Name this session (what are you working on?)\nLeave blank for a timestamped name.");
  if (name === null) return; // user hit Cancel
  try {
    await postJSON("/api/session/start", { name });
    await refreshStatus();
    await loadSessions();
  } catch (err) {
    actionError.textContent = err.message;
  }
});

$("btn-stop").addEventListener("click", async () => {
  actionError.textContent = "";
  try {
    await postJSON("/api/session/stop", {});
    await refreshStatus();
    await loadSessions();
  } catch (err) {
    actionError.textContent = err.message;
  }
});

// ---------- quick note ----------
$("note-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const box = $("note-text");
  const statusEl = $("note-status");
  if (!box.value.trim()) return;
  try {
    const r = await postJSON("/api/notes", { text: box.value });
    box.value = "";
    statusEl.textContent = "Noted at " + r.timestamp + " ✓";
    setTimeout(() => { statusEl.textContent = ""; }, 3000);
    refreshStatus();
  } catch (err) {
    statusEl.textContent = "Failed: " + err.message;
  }
});

// ---------- sessions list ----------
// Newest-first list kept around so the dashboard "Generate Docs" button can
// pick a sensible target (active session, else most recent).
let allSessions = [];

async function loadSessions() {
  const list = $("sessions-list");
  try { allSessions = await api("/api/sessions"); } catch (_) { return; }

  if (!allSessions.length) {
    list.innerHTML =
      '<p class="empty-msg">No sessions yet — click Start Session when you begin lab work.</p>';
    return;
  }
  list.innerHTML = "";
  for (const s of allSessions) {
    const row = document.createElement("div");
    row.className = "session-row" + (s.ended_at ? "" : " session-live");
    const c = s.counts;
    const countsTxt = c
      ? `${c.transcripts} transcripts · ${c.screenshots} screenshots · ${c.notes} notes`
      : "in progress";
    row.innerHTML =
      `<span class="session-name"></span>` +
      `<span class="session-meta">${s.started_at} → ${s.ended_at || "…"}</span>` +
      `<span class="session-meta">${countsTxt}</span>` +
      `<span class="session-actions"></span>`;
    row.querySelector(".session-name").textContent = s.name; // textContent = no HTML injection
    const btn = document.createElement("button");
    btn.className = "row-btn";
    btn.textContent = s.last_generated ? "View docs" : "View / Generate";
    btn.addEventListener("click", () => openReviewForSession(s));
    row.querySelector(".session-actions").appendChild(btn);
    list.appendChild(row);
  }
}

function pickTargetSession() {
  // Prefer the active session; otherwise the most recent (list is newest-first).
  return allSessions.find((s) => !s.ended_at) || allSessions[0] || null;
}

// ---------- synthesis / review (M3) ----------
let reviewSession = null;   // { id, name } currently shown in the review pane

function showView(name) {
  navButtons.forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("view-" + name).classList.remove("hidden");
}

function renderReview(session, data) {
  reviewSession = { id: session.id, name: session.name };
  $("review-empty").classList.add("hidden");
  $("review-body").classList.remove("hidden");
  $("review-session-name").textContent = session.name;
  $("review-session-meta").textContent =
    (data.generated_at ? "Generated " + data.generated_at : "Saved draft") +
    (data.served_by ? " · " + data.served_by : "");
  $("review-rendered").innerHTML = data.html;
  $("review-raw").value = data.markdown;
  $("review-error").textContent = "";
}

async function generateForSession(session) {
  const dashStatus = $("generate-status");
  const reviewStatus = $("review-status");
  const target = reviewSession && reviewSession.id === session.id ? reviewStatus : dashStatus;
  target.textContent = "Generating docs — this can take a minute…";
  target.classList.add("busy");
  $("btn-generate").disabled = true;
  $("btn-regenerate").disabled = true;
  try {
    const data = await postJSON(`/api/session/${session.id}/generate`, {});
    showView("review");
    renderReview(session, data);
    reviewStatus.textContent = "Generated ✓ — review, edit, then commit (M5).";
    reviewStatus.classList.remove("busy");
    dashStatus.textContent = "";
    dashStatus.classList.remove("busy");
    refreshStatus();
    loadSessions();
    setTimeout(() => { reviewStatus.textContent = ""; }, 4000);
  } catch (err) {
    target.classList.remove("busy");
    // If we're already on the review screen, show the error there; else on dashboard.
    if (reviewSession && reviewSession.id === session.id && !$("view-review").classList.contains("hidden")) {
      $("review-error").textContent = err.message;
      reviewStatus.textContent = "";
    } else {
      target.textContent = "";
      $("action-error").textContent = err.message;
    }
  } finally {
    $("btn-generate").disabled = false;
    $("btn-regenerate").disabled = false;
  }
}

async function openReviewForSession(session) {
  // If a doc already exists, open it; otherwise generate a fresh one.
  if (session.last_generated) {
    try {
      const data = await api(`/api/session/${session.id}/doc`);
      showView("review");
      renderReview(session, data);
      return;
    } catch (_) { /* fall through to generate */ }
  }
  generateForSession(session);
}

$("btn-generate").addEventListener("click", () => {
  $("action-error").textContent = "";
  const target = pickTargetSession();
  if (!target) {
    $("action-error").textContent = "No sessions yet — start one and capture some work first.";
    return;
  }
  generateForSession(target);
});

$("btn-regenerate").addEventListener("click", () => {
  if (reviewSession) generateForSession(reviewSession);
});

$("btn-save-doc").addEventListener("click", async () => {
  if (!reviewSession) return;
  const status = $("review-status");
  try {
    const data = await postJSON(`/api/session/${reviewSession.id}/doc`,
      { markdown: $("review-raw").value });
    $("review-rendered").innerHTML = data.html;
    status.textContent = "Edits saved ✓";
    setTimeout(() => { status.textContent = ""; }, 2500);
  } catch (err) {
    $("review-error").textContent = err.message;
  }
});

// Live preview: re-render the rendered pane a moment after the user stops typing.
let renderTimer = null;
$("review-raw").addEventListener("input", () => {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(async () => {
    try {
      const data = await postJSON("/api/render", { markdown: $("review-raw").value });
      $("review-rendered").innerHTML = data.html;
    } catch (_) {}
  }, 400);
});

// ---------- capture agents ----------
async function loadAgents() {
  try {
    const a = await api("/api/agents");
    $("agent-windows").textContent = a.windows;
    $("agent-linux").textContent = a.linux;
    $("agent-share-name").textContent = a.share_name;
    $("agent-shot-path").textContent = a.configured ? "" : "<shared folder>";
    $("agents-unconfigured").textContent = a.configured
      ? ""
      : "Shared capture folder isn't set yet — snippets below use the default name. Set it in Settings first.";
  } catch (_) {}
}

document.querySelectorAll(".copy-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const text = $(btn.dataset.copy).textContent;
    await navigator.clipboard.writeText(text);
    btn.textContent = "Copied ✓";
    setTimeout(() => { btn.textContent = "Copy"; }, 2000);
  });
});

// ---------- settings ----------
const form = $("settings-form");
const fields = {
  shared_folder: $("shared_folder"),
  repo_path: $("repo_path"),
  lab_subnet: $("lab_subnet"),
  api_key: $("api_key"),
};
const saveStatus = $("save-status");
const apiKeyHint = $("api-key-hint");

async function loadSettings() {
  const s = await api("/api/settings");
  fields.shared_folder.value = s.shared_folder;
  fields.repo_path.value = s.repo_path;
  fields.lab_subnet.value = s.lab_subnet;
  // The server never sends the key back — only whether one is saved.
  fields.api_key.value = "";
  if (s.api_key_set) {
    fields.api_key.placeholder = "saved (" + s.api_key_hint + ") — type to replace";
    apiKeyHint.textContent = "A key is saved in .env. Leave blank to keep it.";
  } else {
    fields.api_key.placeholder = "sk-ant-...";
    apiKeyHint.textContent = "Stored locally in .env — never committed, never logged";
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  saveStatus.textContent = "Saving…";
  saveStatus.classList.remove("error");
  try {
    await postJSON("/api/settings", {
      shared_folder: fields.shared_folder.value,
      repo_path: fields.repo_path.value,
      lab_subnet: fields.lab_subnet.value,
      api_key: fields.api_key.value, // empty = keep existing key
    });
    saveStatus.textContent = "Saved ✓";
    await loadSettings();
    await refreshStatus();
    setTimeout(() => { saveStatus.textContent = ""; }, 2500);
  } catch (err) {
    saveStatus.textContent = "Save failed: " + err.message;
    saveStatus.classList.add("error");
  }
});

// ---------- boot ----------
loadSettings();
refreshStatus();
loadSessions();
