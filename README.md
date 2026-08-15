# LabScribe

A Windows desktop app that documents a home cybersecurity lab **while you build it**. It watches your terminal sessions and manually-taken screenshots, then uses the Claude API to turn them into GitHub-ready documentation — a README and a Mermaid network diagram — all driven from a dashboard with a system-tray icon.

I built this because documenting my home SOC lab was competing with actually building it: every fix or finding meant stopping to write it down before I forgot the details, so I was never fully in either mode. LabScribe is the tool that now writes [`home-lab-docs`](https://github.com/DevinCodes13/home-lab-docs) and [`Vulnerability-Management-Workflow`](https://github.com/DevinCodes13/Vulnerability-Management-Workflow) from real captured sessions — it's the thing that made the rest of my portfolio possible to keep up with.

## What It Does

1. **Captures** terminal sessions from Linux (bash/zsh) and Windows (PowerShell) VMs via a small shell snippet — no screen recording, no timed capture, ever
2. **Synthesizes** a session's transcripts, notes, and screenshots into README markdown via the Claude API, with a Troubleshooting Log built from actual command *output* (errors, failures), not just the commands run
3. **Diagrams** the lab network as Mermaid — either from configured inventory, or a live `nmap` sweep that marks hosts up/down and annotates open ports
4. **Commits** the reviewed doc to your repo, running a secret scan first — a high-confidence key pattern (Anthropic/AWS/GitHub/Slack/etc.) blocks the commit outright rather than silently redacting and hoping

## Cost Engineering

Real generations were costing ~$1.00 each with the initial Opus-5-based pipeline. Four changes brought that down to **~$0.05/doc — a 95% reduction** — without a quality drop:

| Change | Why |
|---|---|
| `claude-opus-5` → `claude-sonnet-5` | Near-Opus quality on this structured, well-specified task at a fraction of the cost — the single biggest lever |
| `output_config.effort: "medium"` | Doc synthesis fills in a fixed template from given material — it doesn't need max reasoning depth |
| Prompt caching on the system prompt | The rules + template are identical across generations sharing a diagram — pays off directly when catching up on a backlog of sessions |
| Strip ANSI/VT100 escape codes from transcripts before sending | Raw `script`-captured terminal output is full of cursor-move/redraw/color codes — ~47% size reduction on a noisy real sample, verified with zero content loss |

Verified the cost-reduction request shape was well-formed by sending it with a deliberately invalid API key first and confirming it failed on auth (401), not shape — zero-cost validation before spending anything real.

## Architecture

| Piece | Tool | Why |
|---|---|---|
| Core logic | Python 3.14 | One language for LLM calls, nmap parsing, git |
| Local API | FastAPI + uvicorn | Serves the dashboard, handles button clicks (127.0.0.1 only) |
| App window | pywebview | Native window via Windows WebView2 — no browser tab |
| Tray icon | pystray | Runs quietly in the background |
| Packaging | PyInstaller (one-folder) + Inno Setup | Double-clickable `.exe`; a real installer for sharing with others |

## Troubleshooting Log

Real bugs hit and fixed while building and using this tool day-to-day:

| Issue | Cause | Fix |
|---|---|---|
| A generated doc's host table and network diagram were identical across completely unrelated projects | The diagram cache was a single unscoped file reused for every generation regardless of project, and the README template had a hardcoded host table the model treated as fixed structure rather than session content | Tagged the diagram cache with the subnet it was built for, invalidated on mismatch; replaced the hardcoded table with an explicit instruction to build it fresh from each session's real material |
| Every request to `claude-sonnet-5` failed with a 400 on the `fallbacks` beta parameter | That model doesn't support the server-side refusal-fallback beta yet, unlike the model it replaced | Catch that specific `BadRequestError` and retry as a plain call with no fallback safety net, rather than failing generation outright |
| Kali terminal transcripts appeared frozen at exactly 16,384 bytes no matter how much real activity happened afterward | `script` buffers output in ~4KB chunks when writing to a regular file — not a capture failure, just delayed writes | Added `--flush` to the capture agent's `script` invocation |
| Kali capture agent silently never activated in new terminals | Kali defaults to zsh, not bash — the install snippet was appended to `~/.bashrc`, which zsh never sources | Documented the correct target file per shell; recovered a corrupted `.zshrc` from `/etc/skel/.zshrc` after a bad manual copy-paste fix mid-session |
| Generated docs cited some screenshots but silently dropped others | The prompt asked the model to cite screenshots near their timestamp but didn't make it a hard requirement | Rule now requires every screenshot filename to appear at least once, with an explicit fallback ("additional screenshots from this session: ...") when the exact step isn't clear |

## Privacy & Security Ground Rules

- Capture comes **only** from terminal transcripts and manually-triggered screenshots. No screen recording, no timed capture, ever.
- The Anthropic API key lives in a local `.env` (gitignored) — never in logs, never in generated docs, never sent back to the UI.
- Every commit runs a secret scan over the exact content first; a high-confidence match **blocks** the commit rather than redacting silently.
- Generated docs are always reviewed before anything is committed. LabScribe commits locally — pushing to GitHub stays in your hands.

## How It Works

**Synthesis** — Clicking **Generate Docs** gathers the selected session's transcripts, notes, and screenshot filenames, sends them to `claude-sonnet-5` (streamed), and produces README markdown matching [`templates/readme_template.md`](templates/readme_template.md). Because lab transcripts contain legitimate offensive-security content (Kali, attack/detection scenarios), requests opt into a server-side refusal fallback so authorized, educational material still gets documented.

**Diagram** — Built from configured inventory (always available), or refreshed from a live `nmap -sT -T4 -F -Pn` sweep (a connect scan, no admin rights needed) that marks hosts up/down and annotates open ports. Embedded verbatim into the generated README so it renders natively on GitHub.

**Commit** — From the Review screen, **Commit to repo** writes the reviewed markdown to `README.md`, appends a dated line to `CHANGELOG.md`, and commits both — after the secret scan passes. Auto-commit (off by default) does the same automatically right after generation.

## Status

- [x] **M1** — window + tray + Settings + packaged `.exe`
- [x] **M2** — capture orchestration: sessions, folder watching, notes, agents
- [x] **M3** — synthesis engine: Claude API → README markdown + review screen
- [x] **M4** — diagram generation: nmap sweep / inventory → Mermaid
- [x] **M5** — git integration: review → secret-scan → commit → changelog
- [x] **M6** — packaging & polish: first-run wizard, single-instance guard, tray UX, error handling

**v1.0 — feature-complete.** Full spec: [`docs/LabScribe-SPEC.md`](docs/LabScribe-SPEC.md).

## Running It

**Normal use:** double-click `dist\LabScribe\LabScribe.exe`. Closing the window minimizes to the tray. Settings live in `%APPDATA%\LabScribe\.env`.

**Sharing with other people:** build a real installer instead of handing over the raw `dist\` folder — see [`build/build_exe.md`](build/build_exe.md#building-the-installer-for-sharing-with-other-people). Each person needs their own Anthropic API key; nothing is ever bundled.

**Development:** see [`build/build_exe.md`](build/build_exe.md) for the dev loop and packaging instructions.
