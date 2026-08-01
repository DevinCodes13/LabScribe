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
from labscribe.synthesis import engine
from labscribe.synthesis.render import render_markdown


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


class DocIn(BaseModel):
    markdown: str


class RenderIn(BaseModel):
    markdown: str


def create_app() -> FastAPI:
    app = FastAPI(title="LabScribe", docs_url=None, redoc_url=None)
    static = _static_dir()

    @app.get("/api/health")
    def health():
        return {"status": "ok", "milestone": "M3"}

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

    # ---------- synthesis / docs (M3) ----------

    @app.post("/api/session/{session_id}/generate")
    def generate(session_id: str):
        try:
            result = engine.generate_docs(session_id)
        except engine.SynthesisError as e:
            raise HTTPException(status_code=400, detail=str(e))
        result["html"] = render_markdown(result["markdown"])
        return result

    @app.get("/api/session/{session_id}/doc")
    def read_doc(session_id: str):
        md = engine.get_doc(session_id)
        if md is None:
            raise HTTPException(status_code=404, detail="No document generated yet.")
        return {"session_id": session_id, "markdown": md, "html": render_markdown(md)}

    @app.post("/api/session/{session_id}/doc")
    def write_doc(session_id: str, body: DocIn):
        # Save edits made in the review screen.
        engine.save_doc(session_id, body.markdown)
        return {"session_id": session_id, "html": render_markdown(body.markdown)}

    @app.post("/api/render")
    def render(body: RenderIn):
        # Live preview for the review screen's editor.
        return {"html": render_markdown(body.markdown)}

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app
