"""FastAPI application: serves the dashboard UI and the local settings API.

This server binds to 127.0.0.1 only — it is a private bridge between the
app window and the Python logic, never reachable from the network.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from labscribe.config import settings


def _static_dir() -> Path:
    """Locate the dashboard assets, both in dev and inside the PyInstaller bundle."""
    import sys
    if getattr(sys, "frozen", False):
        # PyInstaller unpacks bundled data files next to the executable
        return Path(sys._MEIPASS) / "dashboard" / "static"
    return Path(__file__).resolve().parents[1] / "dashboard" / "static"


class SettingsIn(BaseModel):
    shared_folder: str = ""
    repo_path: str = ""
    lab_subnet: str = ""
    # Only sent when the user types a new key; empty means "keep existing"
    api_key: str = ""


def create_app() -> FastAPI:
    app = FastAPI(title="LabScribe", docs_url=None, redoc_url=None)
    static = _static_dir()

    @app.get("/api/health")
    def health():
        return {"status": "ok", "milestone": "M1"}

    @app.get("/api/settings")
    def read_settings():
        return settings.get_settings()

    @app.post("/api/settings")
    def write_settings(body: SettingsIn):
        settings.save_settings(
            shared_folder=body.shared_folder,
            repo_path=body.repo_path,
            lab_subnet=body.lab_subnet,
            api_key=body.api_key or None,
        )
        return settings.get_settings()

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app
