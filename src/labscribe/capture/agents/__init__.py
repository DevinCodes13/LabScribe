"""Capture-agent snippet rendering.

The templates contain {{WIN_CAPTURE_PATH}} / {{LINUX_CAPTURE_PATH}}
placeholders. We fill them with the *guest's* view of the shared folder,
derived from the host path's folder name — VirtualBox exposes a share named
"LabCapture" as \\\\VBOXSVR\\LabCapture on Windows guests and
/media/sf_LabCapture on Linux guests. The dashboard tells the user to adjust
if their share name differs.
"""

import sys
from pathlib import Path

from labscribe.config import settings


def _templates_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "capture" / "agents"
    return Path(__file__).resolve().parent


def render_agents() -> dict:
    shared = settings.get_settings()["shared_folder"]
    share_name = Path(shared).name if shared else "LabCapture"

    win = (_templates_dir() / "windows_profile.ps1").read_text(encoding="utf-8")
    lin = (_templates_dir() / "linux_bashrc.sh").read_text(encoding="utf-8")

    return {
        "share_name": share_name,
        "configured": bool(shared),
        "windows": win.replace("{{WIN_CAPTURE_PATH}}", f"\\\\VBOXSVR\\{share_name}"),
        "linux": lin.replace("{{LINUX_CAPTURE_PATH}}", f"/media/sf_{share_name}"),
    }
