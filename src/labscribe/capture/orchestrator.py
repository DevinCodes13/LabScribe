"""Capture session orchestration (Milestone 2).

A "session" is just a named time window. While one is active, anything the
capture agents drop into the shared folder (transcripts, screenshots) whose
modification time falls inside the window belongs to that session. That keeps
LabScribe honest about privacy: it never watches your screen or your VMs —
it only counts and reads files that the agents (or you) deliberately put in
the capture folder.

Why polling instead of filesystem watchers: VirtualBox shared folders often
don't emit change events for writes made by the guest OS, so watchdog-style
APIs silently miss files. Re-scanning the folder on each status request is
reliable and costs microseconds at this scale.

Session records persist in sessions.json next to the .env file
(%APPDATA%\\LabScribe when packaged, repo root when run from source).
"""

import json
import re
from datetime import datetime
from pathlib import Path

from labscribe.config import settings

TIME_FMT = "%Y-%m-%d %H:%M:%S"

# Subfolders the capture agents write into (spec §5.2)
SUBDIRS = ("transcripts", "screenshots", "notes")


class SessionError(Exception):
    """User-facing problem (not configured, no active session, ...)."""


def _sessions_path() -> Path:
    return settings.env_path().parent / "sessions.json"


def _load_sessions() -> list[dict]:
    path = _sessions_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_sessions(sessions: list[dict]) -> None:
    path = _sessions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sessions, indent=2), encoding="utf-8")


def _shared_folder() -> Path:
    folder = settings.get_settings()["shared_folder"]
    if not folder:
        raise SessionError("Set the shared capture folder in Settings first.")
    path = Path(folder)
    if not path.exists():
        raise SessionError(f"Shared capture folder does not exist: {folder}")
    return path


def ensure_capture_dirs() -> Path:
    """Create transcripts/ screenshots/ notes/ inside the shared folder."""
    root = _shared_folder()
    for sub in SUBDIRS:
        (root / sub).mkdir(exist_ok=True)
    return root


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, TIME_FMT)


def in_window(when: datetime, start: datetime | None, end: datetime | None) -> bool:
    """Is `when` inside [start, end], comparing at whole-second precision?

    Stored session timestamps are second-precision (strptime drops microseconds),
    but file mtimes carry sub-second fractions. Without flooring, a file written
    at :43.5 during a session that stopped at :43.0 would be wrongly excluded as
    "after the end". Floor `when` to the second and treat both bounds as inclusive.
    """
    w = when.replace(microsecond=0)
    if start and w < start:
        return False
    if end and w > end:
        return False
    return True


def _count_files(folder: Path, start: datetime | None, end: datetime | None) -> int:
    """Count files in a folder whose mtime falls inside [start, end]."""
    if not folder.exists():
        return 0
    n = 0
    for f in folder.iterdir():
        if not f.is_file():
            continue
        if in_window(datetime.fromtimestamp(f.stat().st_mtime), start, end):
            n += 1
    return n


_NOTE_LINE = re.compile(r"^- \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] ")


def _count_notes(root: Path, start: datetime | None, end: datetime | None) -> int:
    notes_file = root / "notes" / "notes.md"
    if not notes_file.exists():
        return 0
    n = 0
    for line in notes_file.read_text(encoding="utf-8").splitlines():
        m = _NOTE_LINE.match(line)
        if not m:
            continue
        if in_window(_parse(m.group(1)), start, end):
            n += 1
    return n


def counts(start: datetime | None = None, end: datetime | None = None) -> dict:
    """Transcript/screenshot/note counts, optionally limited to a window."""
    try:
        root = _shared_folder()
    except SessionError:
        return {"transcripts": 0, "screenshots": 0, "notes": 0}
    return {
        "transcripts": _count_files(root / "transcripts", start, end),
        "screenshots": _count_files(root / "screenshots", start, end),
        "notes": _count_notes(root, start, end),
    }


def active_session() -> dict | None:
    for s in _load_sessions():
        if s.get("ended_at") is None:
            return s
    return None


def start_session(name: str = "") -> dict:
    if active_session():
        raise SessionError("A session is already running — stop it first.")
    ensure_capture_dirs()  # also validates the shared folder is reachable

    now = datetime.now()
    session = {
        "id": now.strftime("%Y%m%d-%H%M%S"),
        "name": name.strip() or now.strftime("Session %Y-%m-%d %H:%M"),
        "started_at": now.strftime(TIME_FMT),
        "ended_at": None,
        "counts": None,
    }
    sessions = _load_sessions()
    sessions.append(session)
    _save_sessions(sessions)
    return session


def stop_session() -> dict:
    sessions = _load_sessions()
    for s in sessions:
        if s.get("ended_at") is None:
            end = datetime.now()
            s["ended_at"] = end.strftime(TIME_FMT)
            # Snapshot final counts so past sessions don't need rescanning
            s["counts"] = counts(_parse(s["started_at"]), end)
            _save_sessions(sessions)
            return s
    raise SessionError("No session is running.")


def list_sessions() -> list[dict]:
    """Past + current sessions, newest first."""
    return list(reversed(_load_sessions()))


def status() -> dict:
    """Everything the dashboard status panel needs, in one call."""
    cfg = settings.get_settings()
    active = active_session()
    if active:
        current = counts(_parse(active["started_at"]), None)
    else:
        current = counts()  # idle: show all-time folder totals
    # Most recent doc-generation timestamp across all sessions (set in M3).
    generated = [s["last_generated"] for s in _load_sessions()
                 if s.get("last_generated")]
    last_generated = max(generated) if generated else None

    return {
        "configured": bool(cfg["shared_folder"]),
        "shared_folder_ok": bool(cfg["shared_folder"])
        and Path(cfg["shared_folder"]).exists(),
        "active": active,
        "counts": current,
        "last_generated": last_generated,
    }


def add_note(text: str) -> dict:
    text = " ".join(text.split())  # collapse newlines: one note = one line
    if not text:
        raise SessionError("Note is empty.")
    root = ensure_capture_dirs()
    notes_file = root / "notes" / "notes.md"
    stamp = datetime.now().strftime(TIME_FMT)
    with open(notes_file, "a", encoding="utf-8") as f:
        f.write(f"- [{stamp}] {text}\n")
    return {"saved": True, "timestamp": stamp}
