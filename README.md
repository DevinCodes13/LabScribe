# LabScribe

A Windows desktop app that documents a home cybersecurity lab **for** you.
While you build your lab in VirtualBox VMs, LabScribe collects terminal
transcripts, manually-taken screenshots, and quick notes — then uses the
Anthropic API to turn them into GitHub-ready documentation (README +
Mermaid network diagram), all driven from a dashboard with a system-tray
icon. Full specification: [docs/LabScribe-SPEC.md](docs/LabScribe-SPEC.md).

## Stack (Option A from the spec)

| Piece | Tool | Why |
|---|---|---|
| Core logic | Python 3.14 | One language for LLM calls, nmap parsing, git |
| Local API | FastAPI + uvicorn | Serves the dashboard, handles button clicks (127.0.0.1 only) |
| App window | pywebview | Native window via Windows WebView2 — no browser tab |
| Tray icon | pystray | Runs quietly in the background; Quit lives here |
| Packaging | PyInstaller (one-folder) | Double-clickable `LabScribe.exe`, no Python needed |

## Privacy & security ground rules

- Capture comes **only** from terminal transcripts and manually-triggered
  screenshots. There is no screen recording and no timed capture, ever.
- The Anthropic API key lives in a local `.env` (gitignored) — never in
  logs, never in generated docs, never sent back to the UI.
- Generated docs are always reviewed by you before anything is committed.

## Status

- [x] **M1 — Skeleton**: window + tray + Settings screen + packaged .exe
- [x] **M2 — Capture orchestration**: sessions, folder watching, notes, agents
- [x] **M3 — Synthesis engine**: Anthropic API → README markdown + review screen
- [x] **M4 — Diagram generation**: nmap sweep / inventory → Mermaid, embedded in README
- [x] **M5 — Git integration**: review → secret-scan → commit; changelog; auto-commit opt-in
- [x] **M6 — Packaging & polish**: first-run wizard, single-instance guard, tray UX, error handling

**v1.0 — feature-complete.** LabScribe captures lab work, synthesizes README docs
with an LLM, generates a network diagram, and commits to your repo — all from a
double-clickable `.exe`, no terminal needed.

## Live troubleshooting alerts (bonus, post-v1.0)

While a session is running, a background thread tails the active transcript
files and pops a tray notification the instant a line looks like an error or
warning ("Possible issue on DC01 — WARNING: A delegation for this DNS server
cannot be created — consider a screenshot") — a nudge to grab a screenshot
*now*, while the exact wording is still on screen.

This adds **no new capture surface**: it only reads the transcript text
LabScribe already collects during an active session (opt-in, from lab VMs
you've installed a capture snippet in) — it never touches your screen, other
windows, or anything outside those recorded terminals. It's tied 1:1 to
session state (silent the moment you're not recording), debounced so a burst
of errors triggers one notification instead of a flood, and redacts the
same secret patterns used before a git commit so a notification can never
surface a live credential a failing command happened to echo back.

## First run & polish (M6)

- **Setup wizard** — on first launch (nothing configured) a 3-step wizard collects
  your capture folder, repo path, subnet, and API key, then opens the dashboard.
- **Single instance** — launching LabScribe while it's already running just tells
  you to check the tray and exits, instead of starting a second copy.
- **Tray** — Show Dashboard · Start/Stop Session · Generate Docs · Quit, with a
  one-time "still running in the tray" notice the first time you close the window.
- **Startup errors** — a fatal startup problem (e.g. a missing WebView2 runtime)
  shows a dialog with the fix and writes details to `%APPDATA%\LabScribe\labscribe.log`.

## How committing works (M5)

From the **Review Docs** screen, **Commit to repo** writes the reviewed markdown
to `README.md` and appends a dated line to `CHANGELOG.md` in your configured
repo, then `git commit`s both. Before writing anything, a **secret scan** runs
over the exact content — if it finds a high-confidence key pattern (Anthropic /
OpenAI / AWS / GitHub / Google / Slack tokens, or a private-key block) the commit
is **blocked** and the finding is shown (masked) so you can redact it in the
editor and retry. Nothing partial is ever written.

**Auto-commit** (Settings, off by default) commits automatically right after a
doc is generated — the same secret scan still runs and still blocks on findings.
LabScribe commits locally; pushing to GitHub stays in your hands.

## How the network diagram works (M4)

The **Network Diagram** screen builds a Mermaid diagram of the lab two ways:

- **Build from inventory** — always available, no nmap needed. Lays out the
  known lab hosts (DC / workstation / SIEM / attacker) on your configured subnet.
- **Refresh from live scan (nmap)** — runs `nmap -sT -T4 -F -Pn` against the lab
  subnet (a connect scan, so no admin rights needed), marks each host up/down,
  annotates open ports, and surfaces any unexpected live hosts. Requires
  [nmap](https://nmap.org/download) installed on the host; the app degrades
  cleanly with an install hint if it isn't.

The diagram is saved and embedded verbatim into the generated README's Network
Diagram section (it renders natively on GitHub). The in-app preview uses a
locally bundled `mermaid.min.js` — no internet needed at runtime.

## How synthesis works (M3)

Clicking **Generate Docs** gathers the selected session's transcripts, quick
notes, and screenshot filenames, sends them to the Anthropic API
(`claude-opus-5`, streamed), and produces README markdown in the format from
[templates/readme_template.md](templates/readme_template.md). The **Review Docs**
screen shows the result rendered next to editable raw markdown — edit, regenerate,
or (from M5) commit. Because lab transcripts contain legitimate offensive-security
content, requests opt into a server-side refusal fallback to `claude-opus-4-8` so
authorized, educational lab material still gets documented.

## Running it

**Normal use:** double-click `dist\LabScribe\LabScribe.exe`. Closing the
window minimizes to the tray; right-click the tray icon → Quit to exit.
Settings are stored in `%APPDATA%\LabScribe\.env`.

**Sharing with other people:** build a real installer instead of handing over
the raw `dist\` folder — see [build/build_exe.md](build/build_exe.md#building-the-installer-for-sharing-with-other-people).
Each person needs their own Anthropic API key; nothing is ever bundled.

**Development:** see [build/build_exe.md](build/build_exe.md) for the dev
loop and packaging instructions.
