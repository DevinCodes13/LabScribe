"""Settings storage for LabScribe.

All four user settings live in a single .env file:

  - LABSCRIBE_SHARED_FOLDER   where the lab VMs drop transcripts/screenshots/notes
  - LABSCRIBE_REPO_PATH       the git repo LabScribe documents into
  - LABSCRIBE_LAB_SUBNET      subnet for nmap discovery (M4)
  - ANTHROPIC_API_KEY         used for doc synthesis (M3)

Where the .env lives depends on how we're running:

  - Running from source (development): <repo root>/.env, which is gitignored.
  - Running as the packaged .exe:      %APPDATA%\\LabScribe\\.env

The packaged app uses %APPDATA% because the install folder may not be writable
and because settings should survive replacing the .exe with a newer build.

Security rule (spec R4): the API key is never logged and never echoed back in
full — get_settings() only reports whether a key is saved, plus its last four
characters so the user can tell keys apart.
"""

import os
import sys
from pathlib import Path

from dotenv import dotenv_values

# Keys as they appear in the .env file
_ENV_KEYS = {
    "shared_folder": "LABSCRIBE_SHARED_FOLDER",
    "repo_path": "LABSCRIBE_REPO_PATH",
    "lab_subnet": "LABSCRIBE_LAB_SUBNET",
    "api_key": "ANTHROPIC_API_KEY",
}

DEFAULT_SUBNET = "10.10.10.0/24"


def is_frozen() -> bool:
    """True when running as a PyInstaller-built .exe."""
    return getattr(sys, "frozen", False)


def env_path() -> Path:
    if is_frozen():
        return Path(os.environ["APPDATA"]) / "LabScribe" / ".env"
    # settings.py -> config -> labscribe -> src -> repo root
    return Path(__file__).resolve().parents[3] / ".env"


def _read() -> dict:
    path = env_path()
    if not path.exists():
        return {}
    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def get_settings() -> dict:
    """Settings for display in the UI. The API key itself is never included."""
    raw = _read()
    api_key = raw.get(_ENV_KEYS["api_key"], "")
    return {
        "shared_folder": raw.get(_ENV_KEYS["shared_folder"], ""),
        "repo_path": raw.get(_ENV_KEYS["repo_path"], ""),
        "lab_subnet": raw.get(_ENV_KEYS["lab_subnet"], DEFAULT_SUBNET),
        "api_key_set": bool(api_key),
        "api_key_hint": ("..." + api_key[-4:]) if len(api_key) >= 8 else "",
    }


def get_api_key() -> str:
    """Full API key, for internal use by the synthesis engine only (M3)."""
    return _read().get(_ENV_KEYS["api_key"], "")


def save_settings(shared_folder: str, repo_path: str, lab_subnet: str,
                  api_key: str | None) -> None:
    """Write settings to the .env file.

    api_key=None (or empty) means "keep the existing key" — the UI sends the
    key only when the user actually types a new one, so a normal settings save
    can't accidentally wipe it.
    """
    current = _read()
    current[_ENV_KEYS["shared_folder"]] = shared_folder.strip()
    current[_ENV_KEYS["repo_path"]] = repo_path.strip()
    current[_ENV_KEYS["lab_subnet"]] = lab_subnet.strip() or DEFAULT_SUBNET
    if api_key:
        current[_ENV_KEYS["api_key"]] = api_key.strip()

    path = env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in current.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def clear_api_key() -> None:
    current = _read()
    current.pop(_ENV_KEYS["api_key"], None)
    path = env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in current.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
