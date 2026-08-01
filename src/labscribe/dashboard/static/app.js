// LabScribe dashboard logic — plain JS, no framework.
// Talks to the local FastAPI server over /api/*.

// ---------- view switching ----------
const navButtons = document.querySelectorAll(".nav-btn");
navButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    navButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
    document.getElementById("view-" + btn.dataset.view).classList.remove("hidden");
  });
});

// ---------- settings ----------
const form = document.getElementById("settings-form");
const fields = {
  shared_folder: document.getElementById("shared_folder"),
  repo_path: document.getElementById("repo_path"),
  lab_subnet: document.getElementById("lab_subnet"),
  api_key: document.getElementById("api_key"),
};
const saveStatus = document.getElementById("save-status");
const apiKeyHint = document.getElementById("api-key-hint");
const configHint = document.getElementById("config-hint");

async function loadSettings() {
  const res = await fetch("/api/settings");
  const s = await res.json();
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
  configHint.textContent = (!s.shared_folder || !s.repo_path)
    ? "Not configured yet — open Settings to set your capture folder and repo path."
    : "";
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  saveStatus.textContent = "Saving…";
  saveStatus.classList.remove("error");
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        shared_folder: fields.shared_folder.value,
        repo_path: fields.repo_path.value,
        lab_subnet: fields.lab_subnet.value,
        api_key: fields.api_key.value, // empty = keep existing key
      }),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    saveStatus.textContent = "Saved ✓";
    await loadSettings();
    setTimeout(() => { saveStatus.textContent = ""; }, 2500);
  } catch (err) {
    saveStatus.textContent = "Save failed: " + err.message;
    saveStatus.classList.add("error");
  }
});

loadSettings();
