"""Live troubleshooting watcher (bonus, post-v1.0).

Tails an active session's transcript files and pops a tray notification the
moment a line looks like an error or warning — a nudge to grab a screenshot
*right now*, while the exact wording is still on screen.

This adds NO new capture surface. It only reads the transcript text files
LabScribe already collects (opt-in, per spec §5.1, only from lab terminals the
user installed a capture snippet in) while a session is running. It never
touches the screen, other windows, or any application outside those recorded
terminal sessions — same boundary as the rest of LabScribe (spec R3).

Design notes:
  - Polls rather than using filesystem-change events, for the same reason
    orchestrator.py polls: VirtualBox shared folders don't reliably emit
    change events for guest writes. A few seconds of notification latency is
    a fine trade-off for reliability.
  - Tracks a byte offset per transcript file so each poll only scans newly
    appended text, not the whole file every cycle.
  - Globally debounced: one cooldown window means a burst of matching lines
    (e.g. a 15-line stack trace) fires a single notification, not fifteen.
  - The matched line is redacted with the same patterns used before a git
    commit, so a notification can never surface a live secret even if the
    failing command that produced the error echoed one back.
  - Decoupled from the actual notification mechanism via set_notifier(), so
    this module has no dependency on pystray — app.py wires the tray icon in;
    dev/server-only mode falls back to a stdout print.
"""

import re
import threading
import time
from datetime import datetime
from pathlib import Path

from labscribe.capture.orchestrator import _parse, in_window
from labscribe.config import settings
from labscribe.gitio.repo import redact_secrets

POLL_SECONDS = 4
NOTIFY_COOLDOWN_SECONDS = 60
PREVIEW_MAX_CHARS = 70

# High-signal words only — chosen so ordinary lab output ("Success", "Restart
# Needed", "Continue anyway?") never matches, while genuine problems
# (PowerShell warnings, failed commands, denied access) reliably do.
_PROBLEM_PATTERN = re.compile(
    r"\b(error|fail(?:ed|ure)?|denied|exception|cannot|unable|"
    r"not[- ]found|timed?[- ]?out|refused|invalid|warning)\b",
    re.IGNORECASE,
)

_notify = None
_thread: threading.Thread | None = None
_stop_event = threading.Event()


def set_notifier(fn) -> None:
    """Register how to actually alert the user: fn(message: str) -> None."""
    global _notify
    _notify = fn


def _notify_user(message: str) -> None:
    if _notify:
        try:
            _notify(message)
            return
        except Exception:
            pass
    print(f"[LabScribe watcher] {message}")


def _hostname_from_filename(path: Path) -> str:
    # Transcript names are "<date>_<time>_<hostname>.txt" (see capture/agents).
    parts = path.stem.split("_", 2)
    return parts[-1] if len(parts) == 3 else path.name


def _preview(line: str) -> str:
    line = redact_secrets(line.strip())
    if len(line) > PREVIEW_MAX_CHARS:
        line = line[:PREVIEW_MAX_CHARS].rstrip() + "…"
    return line


def _poll_loop(started_at: datetime) -> None:
    offsets: dict[Path, int] = {}
    last_notified = 0.0

    while True:
        try:
            shared = settings.get_settings()["shared_folder"]
            tdir = Path(shared) / "transcripts" if shared else None
            if tdir and tdir.exists():
                now = time.monotonic()
                for f in tdir.iterdir():
                    if not f.is_file():
                        continue
                    if not in_window(
                        datetime.fromtimestamp(f.stat().st_mtime), started_at, None
                    ):
                        continue  # not part of this session

                    offset = offsets.get(f, 0)
                    try:
                        with f.open("r", encoding="utf-8", errors="replace") as fh:
                            fh.seek(offset)
                            new_text = fh.read()
                            offsets[f] = fh.tell()
                    except OSError:
                        continue

                    if not new_text or now - last_notified < NOTIFY_COOLDOWN_SECONDS:
                        continue

                    for line in new_text.splitlines():
                        if _PROBLEM_PATTERN.search(line):
                            host = _hostname_from_filename(f)
                            _notify_user(
                                f"Possible issue on {host} — {_preview(line)} "
                                "— consider a screenshot"
                            )
                            last_notified = now
                            break
        except Exception:
            pass  # a watcher hiccup must never take down the session

        if _stop_event.wait(POLL_SECONDS):
            break  # stop() was called


def start(session: dict) -> None:
    """Begin watching this session's transcripts. No-op if already running."""
    global _thread
    if _thread and _thread.is_alive():
        return
    started_at = _parse(session["started_at"])
    _stop_event.clear()
    _thread = threading.Thread(
        target=_poll_loop, args=(started_at,), daemon=True, name="labscribe-watcher"
    )
    _thread.start()


def stop() -> None:
    _stop_event.set()
