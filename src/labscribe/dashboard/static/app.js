// LabScribe dashboard logic — plain JS, no framework.
// Talks to the local FastAPI server over /api/*.

// ---------- small helpers ----------
const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = "HTTP " + res.status;
    try { detail = (await res.json()).detail ?? detail; } catch (_) {}
    // detail may be a string or a structured object (e.g. secret findings).
    const err = new Error(typeof detail === "string" ? detail : (detail.message || "Request failed"));
    err.detail = detail;
    throw err;
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

// ---------- mermaid init (bundled locally, no CDN) ----------
if (window.mermaid) {
  window.mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "loose" });
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
    if (btn.dataset.view === "diagram") loadDiagram();
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
    reviewStatus.textContent = "Generated ✓ — review, edit, then commit.";
    // If auto-commit is on, report what happened right in the review screen.
    if (data.auto_commit) {
      if (data.auto_commit.ok) {
        reviewStatus.textContent =
          `Generated & auto-committed ${data.auto_commit.commit} to ${data.auto_commit.branch} ✓`;
      } else {
        $("review-error").textContent = "Auto-commit failed: " + data.auto_commit.message;
        showCommitFindings(data.auto_commit.message, data.auto_commit.findings);
      }
    }
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

function showCommitFindings(message, findings) {
  const box = $("commit-result");
  if (!findings || !findings.length) { box.innerHTML = ""; return; }
  const items = findings.map((f) => {
    const li = document.createElement("li");
    li.textContent = `line ${f.line}: ${f.type} (${f.preview})`;
    return li.outerHTML;
  }).join("");
  const msg = document.createElement("div");
  msg.textContent = message;
  box.innerHTML =
    `<div class="commit-findings">${msg.outerHTML}` +
    `<ul>${items}</ul>` +
    `<div>Redact these in the editor and commit again.</div></div>`;
}

$("btn-commit").addEventListener("click", async () => {
  if (!reviewSession) return;
  const status = $("review-status");
  const err = $("review-error");
  err.textContent = "";
  $("commit-result").innerHTML = "";
  status.textContent = "Committing to repo…";
  status.classList.add("busy");
  $("btn-commit").disabled = true;
  try {
    const r = await postJSON(`/api/session/${reviewSession.id}/commit`,
      { markdown: $("review-raw").value });
    status.classList.remove("busy");
    status.textContent = `Committed ${r.commit} to ${r.branch} ✓ (${r.files.join(", ")})`;
  } catch (e) {
    status.textContent = ""; status.classList.remove("busy");
    // Secret-scan blocks arrive as a structured detail {message, findings}.
    let detail = e.detail;
    if (detail && typeof detail === "object") {
      err.textContent = detail.message || "Commit failed.";
      showCommitFindings(detail.message || "", detail.findings);
    } else {
      err.textContent = e.message;
    }
  } finally {
    $("btn-commit").disabled = false;
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

// ---------- network diagram (M4) ----------
let mermaidSeq = 0;

async function drawMermaid(text) {
  const el = $("diagram-render");
  if (!window.mermaid) {
    el.innerHTML = '<div class="diagram-fallback">Diagram preview unavailable — see the Mermaid source below (it renders on GitHub).</div>';
    return;
  }
  try {
    const { svg } = await window.mermaid.render("m" + (++mermaidSeq), text);
    el.innerHTML = svg;
  } catch (err) {
    el.innerHTML = '<div class="diagram-fallback">Couldn\'t render preview: ' +
      (err && err.message ? err.message : "error") +
      '. The Mermaid source below still renders on GitHub.</div>';
  }
}

function renderHostTable(hosts) {
  const wrap = $("host-table");
  if (!hosts || !hosts.length) { wrap.innerHTML = '<p class="empty-msg">No hosts.</p>'; return; }
  const pill = (s) =>
    `<span class="status-pill status-${s}">${s.toUpperCase()}</span>`;
  const rows = hosts.map((h) => {
    const td = document.createElement("template");
    // Build cells with textContent to avoid injecting scan-derived strings as HTML.
    const cells = [h.name, h.ip, h.os, h.role].map((v) => {
      const c = document.createElement("td"); c.textContent = v; return c.outerHTML;
    });
    const portsCell = document.createElement("td");
    portsCell.textContent = (h.ports && h.ports.length) ? h.ports.join(", ") : "—";
    return `<tr>${cells[0]}<td>${pill(h.status)}</td>${cells[1]}${cells[2]}${cells[3]}${portsCell.outerHTML}</tr>`;
  }).join("");
  wrap.innerHTML =
    `<table class="host-table"><thead><tr>` +
    `<th>Host</th><th>Status</th><th>IP</th><th>OS</th><th>Role</th><th>Open ports</th>` +
    `</tr></thead><tbody>${rows}</tbody></table>`;
}

function applyDiagram(data) {
  $("diagram-source").textContent = data.mermaid;
  renderHostTable(data.hosts);
  drawMermaid(data.mermaid);
  const hint = $("nmap-hint");
  hint.textContent = data.nmap_available
    ? ""
    : "nmap not detected — live scanning is disabled. Install nmap (with Npcap) from nmap.org to scan the running lab; 'Build from inventory' works without it.";
}

async function loadDiagram() {
  try {
    applyDiagram(await api("/api/diagram"));
  } catch (_) {}
}

async function refreshDiagram(mode) {
  const err = $("diagram-error");
  const status = $("diagram-status");
  err.textContent = "";
  status.textContent = mode === "scan"
    ? "Scanning the lab subnet — this can take a minute…"
    : "Building diagram from inventory…";
  status.classList.add("busy");
  $("btn-scan").disabled = true; $("btn-config").disabled = true;
  try {
    const data = await postJSON("/api/diagram/refresh?mode=" + mode, {});
    applyDiagram(data);
    status.classList.remove("busy");
    status.textContent = (mode === "scan" ? "Scan complete" : "Diagram built") +
      " ✓ " + (data.refreshed_at || "");
    setTimeout(() => { status.textContent = ""; }, 4000);
  } catch (e) {
    status.textContent = ""; status.classList.remove("busy");
    err.textContent = e.message;
  } finally {
    $("btn-scan").disabled = false; $("btn-config").disabled = false;
  }
}

$("btn-scan").addEventListener("click", () => refreshDiagram("scan"));
$("btn-config").addEventListener("click", () => refreshDiagram("config"));

// Dashboard "Refresh Diagram" opens the diagram view and runs a live scan.
$("btn-refresh-diagram").addEventListener("click", () => {
  showView("diagram");
  refreshDiagram("scan");
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
  auto_commit: $("auto_commit"),
};
const saveStatus = $("save-status");
const apiKeyHint = $("api-key-hint");

async function loadRepoStatus() {
  const el = $("repo-status");
  try {
    const r = await api("/api/repo/status");
    el.classList.remove("ok", "warn");
    if (!r.path) { el.textContent = ""; return; }
    if (r.is_repo) {
      el.textContent = `Git repo detected on branch ${r.branch}.`;
      el.classList.add("ok");
    } else if (r.exists) {
      el.textContent = "Folder exists but is not a git repository — run `git init` there or point at your cloned repo.";
      el.classList.add("warn");
    } else {
      el.textContent = "Path does not exist yet.";
      el.classList.add("warn");
    }
  } catch (_) { el.textContent = ""; }
}

async function loadSettings() {
  const s = await api("/api/settings");
  fields.shared_folder.value = s.shared_folder;
  fields.repo_path.value = s.repo_path;
  fields.lab_subnet.value = s.lab_subnet;
  fields.auto_commit.checked = !!s.auto_commit;
  // The server never sends the key back — only whether one is saved.
  fields.api_key.value = "";
  if (s.api_key_set) {
    fields.api_key.placeholder = "saved (" + s.api_key_hint + ") — type to replace";
    apiKeyHint.textContent = "A key is saved in .env. Leave blank to keep it.";
  } else {
    fields.api_key.placeholder = "sk-ant-...";
    apiKeyHint.textContent = "Stored locally in .env — never committed, never logged";
  }
  loadRepoStatus();
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
      auto_commit: fields.auto_commit.checked,
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
