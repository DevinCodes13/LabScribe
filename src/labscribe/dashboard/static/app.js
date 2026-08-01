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
async function loadSessions() {
  const list = $("sessions-list");
  let sessions;
  try { sessions = await api("/api/sessions"); } catch (_) { return; }

  if (!sessions.length) {
    list.innerHTML =
      '<p class="empty-msg">No sessions yet — click Start Session when you begin lab work.</p>';
    return;
  }
  list.innerHTML = "";
  for (const s of sessions) {
    const row = document.createElement("div");
    row.className = "session-row" + (s.ended_at ? "" : " session-live");
    const c = s.counts;
    const countsTxt = c
      ? `${c.transcripts} transcripts · ${c.screenshots} screenshots · ${c.notes} notes`
      : "in progress";
    row.innerHTML =
      `<span class="session-name"></span>` +
      `<span class="session-meta">${s.started_at} → ${s.ended_at || "…"}</span>` +
      `<span class="session-meta">${countsTxt}</span>`;
    row.querySelector(".session-name").textContent = s.name; // textContent = no HTML injection
    list.appendChild(row);
  }
}

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
