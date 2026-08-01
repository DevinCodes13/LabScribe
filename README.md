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
- [ ] M2 — Capture orchestration
- [ ] M3 — Synthesis engine (Anthropic API)
- [ ] M4 — nmap → Mermaid diagram
- [ ] M5 — Git integration
- [ ] M6 — Packaging polish + first-run wizard

## Running it

**Normal use:** double-click `dist\LabScribe\LabScribe.exe`. Closing the
window minimizes to the tray; right-click the tray icon → Quit to exit.
Settings are stored in `%APPDATA%\LabScribe\.env`.

**Development:** see [build/build_exe.md](build/build_exe.md) for the dev
loop and packaging instructions.
