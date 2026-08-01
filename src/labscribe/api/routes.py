"""FastAPI application: serves the dashboard UI and the local settings API.

This server binds to 127.0.0.1 only — it is a private bridge between the
app window and the Python logic, never reachable from the network.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from labscribe.capture import orchestrator
from labscribe.capture.agents import render_agents
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


class SessionIn(BaseModel):
    name: str = ""


class NoteIn(BaseModel):
    text: str


def create_app() -> FastAPI:
    app = FastAPI(title="LabScribe", docs_url=None, redoc_url=None)
    static = _static_dir()

    @app.get("/api/health")
    def health():
        return {"status": "ok", "milestone": "M2"}

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

    # ---------- capture sessions (M2) ----------
    # SessionError means "user-facing problem" (folder missing, no session
    # running, ...) — map it to HTTP 400 so the UI can show the message.

    @app.get("/api/status")
    def read_status():
        return orchestrator.status()

    @app.post("/api/session/start")
    def session_start(body: SessionIn):
        try:
            return orchestrator.start_session(body.name)
        except orchestrator.SessionError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/session/stop")
    def session_stop():
        try:
            return orchestrator.stop_session()
        except orchestrator.SessionError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/sessions")
    def sessions():
        return orchestrator.list_sessions()

    @app.post("/api/notes")
    def add_note(body: NoteIn):
        try:
            return orchestrator.add_note(body.text)
        except orchestrator.SessionError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/agents")
    def agents():
        return render_agents()

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app
