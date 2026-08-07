"""Synthesis engine: turn a captured session into README markdown via the API.

Flow (spec 5.3):
  1. Gather the session's transcripts, notes, and screenshot filenames.
  2. Send them to the Anthropic API with the target-format system prompt.
  3. Return the generated Markdown for the review screen; also save a copy so
     the doc persists and can be reopened later.

Model choice: claude-opus-5, streamed so long documents don't hit request
timeouts. We opt into server-side refusal fallbacks to claude-opus-4-8 because
lab transcripts contain legitimate offensive-security content (nmap, Kali,
attack/detection scenarios) that Opus 5's cyber-safety classifier can otherwise
decline — the fallback keeps documentation generation working for authorized,
educational lab material.

Security: the Anthropic API key is read only from settings and is never logged
or written into generated docs. Any secret-looking values in the transcripts are
the model's job to redact per the system prompt.
"""

import sys
from datetime import datetime
from pathlib import Path

import anthropic

from labscribe.capture import orchestrator
from labscribe.config import settings
from labscribe.synthesis import prompts

MODEL = "claude-sonnet-5"
FALLBACK_MODEL = "claude-opus-4-8"
MAX_OUTPUT_TOKENS = 20000
# Doc synthesis is a well-specified task (fill in a given template from given
# material), not open-ended exploration — "medium" effort holds quality while
# cutting the thinking-token spend "high" (the API default) would otherwise use.
EFFORT = "medium"
# Total character budget for transcript text sent in one request. Opus 5 has a
# 1M-token context window, but there's no reason to send more than this for a
# single lab session — it keeps requests fast and cheap.
MAX_TRANSCRIPT_CHARS = 200_000


class SynthesisError(Exception):
    """User-facing synthesis problem (no key, nothing to synthesize, API error)."""


def _templates_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "templates"
    # engine.py -> synthesis -> labscribe -> src -> repo root
    return Path(__file__).resolve().parents[3] / "templates"


def load_template() -> str:
    path = _templates_dir() / "readme_template.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _generated_dir() -> Path:
    d = settings.env_path().parent / "generated"
    d.mkdir(parents=True, exist_ok=True)
    return d


def doc_path(session_id: str) -> Path:
    return _generated_dir() / f"{session_id}.md"


def get_doc(session_id: str) -> str | None:
    p = doc_path(session_id)
    return p.read_text(encoding="utf-8") if p.exists() else None


def save_doc(session_id: str, markdown: str) -> None:
    doc_path(session_id).write_text(markdown, encoding="utf-8")


def _find_session(session_id: str) -> dict | None:
    for s in orchestrator._load_sessions():
        if s["id"] == session_id:
            return s
    return None


def _mark_generated(session_id: str) -> None:
    sessions = orchestrator._load_sessions()
    stamp = datetime.now().strftime(orchestrator.TIME_FMT)
    for s in sessions:
        if s["id"] == session_id:
            s["last_generated"] = stamp
            break
    orchestrator._save_sessions(sessions)


def gather_material(session: dict) -> tuple[list[dict], list[dict], list[str]]:
    """Collect transcripts, screenshot filenames, and notes for the session window."""
    root = orchestrator._shared_folder()  # raises SessionError if unset/missing
    start = orchestrator._parse(session["started_at"])
    end = orchestrator._parse(session["ended_at"]) if session.get("ended_at") else None

    def within(when: datetime) -> bool:
        return orchestrator.in_window(when, start, end)

    transcripts: list[dict] = []
    tdir = root / "transcripts"
    if tdir.exists():
        for f in sorted(tdir.iterdir()):
            if f.is_file() and within(datetime.fromtimestamp(f.stat().st_mtime)):
                try:
                    transcripts.append(
                        {"name": f.name,
                         "text": f.read_text(encoding="utf-8", errors="replace")}
                    )
                except OSError:
                    pass

    # Screenshots carry their capture timestamp (not just the filename) so the
    # model can place each citation at the right point in the transcript
    # timeline instead of just being handed an unanchored list of names.
    screenshots: list[dict] = []
    sdir = root / "screenshots"
    if sdir.exists():
        for f in sorted(sdir.iterdir()):
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if within(mtime):
                    screenshots.append({"name": f.name, "taken_at": mtime})
    screenshots.sort(key=lambda s: s["taken_at"])

    notes: list[str] = []
    notes_file = root / "notes" / "notes.md"
    if notes_file.exists():
        for line in notes_file.read_text(encoding="utf-8").splitlines():
            m = orchestrator._NOTE_LINE.match(line)
            if m and within(orchestrator._parse(m.group(1))):
                notes.append(line)

    return transcripts, screenshots, notes


def _call_model(api_key: str, system: str, user_content: str):
    """Stream the request with refusal fallback; degrade gracefully on old SDKs.

    The system prompt (rules + full README template) is identical across
    generations that share the same network diagram, so it's marked
    cacheable — a near-free addition that pays off whenever docs are
    generated for several sessions back-to-back (a real, common pattern:
    catching up on a backlog).
    """
    client = anthropic.Anthropic(api_key=api_key)
    kwargs = dict(
        model=MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": EFFORT},
        messages=[{"role": "user", "content": user_content}],
    )
    # Preferred path: beta streaming with server-side refusal fallback.
    try:
        with client.beta.messages.stream(
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": FALLBACK_MODEL}],
            **kwargs,
        ) as stream:
            return stream.get_final_message()
    except TypeError:
        # SDK too old for betas/fallbacks — fall back to a plain streamed call.
        with client.messages.stream(**kwargs) as stream:
            return stream.get_final_message()


def generate_docs(session_id: str) -> dict:
    api_key = settings.get_api_key()
    if not api_key:
        raise SynthesisError("No Anthropic API key saved. Add it in Settings first.")

    session = _find_session(session_id)
    if not session:
        raise SynthesisError("Session not found.")

    transcripts, screenshots, notes = gather_material(session)
    if not transcripts and not notes:
        raise SynthesisError(
            "This session has no transcripts or notes yet — nothing to document."
        )

    cfg = settings.get_settings()
    # Pre-fill the template's diagram placeholder with the real, deterministically
    # generated network diagram (from the last nmap refresh, else config-only) so
    # the model reproduces it verbatim instead of inventing one.
    from labscribe import diagram
    template = load_template().replace(
        "{{MERMAID_DIAGRAM}}", diagram.diagram_for_readme(cfg["lab_subnet"])
    )
    system = prompts.SYSTEM_PROMPT.replace("{{TEMPLATE}}", template)
    user_content = prompts.build_user_message(
        session, transcripts, screenshots, notes,
        cfg["lab_subnet"], MAX_TRANSCRIPT_CHARS,
    )

    try:
        message = _call_model(api_key, system, user_content)
    except anthropic.AuthenticationError:
        raise SynthesisError("Anthropic API key was rejected. Check it in Settings.")
    except anthropic.RateLimitError:
        raise SynthesisError("Anthropic rate limit hit. Wait a moment and try again.")
    except anthropic.APIConnectionError:
        raise SynthesisError("Couldn't reach the Anthropic API. Check your connection.")
    except anthropic.APIError as e:
        raise SynthesisError(f"Anthropic API error: {e}")

    if message.stop_reason == "refusal":
        raise SynthesisError(
            "The model declined to generate this document, even with fallback. "
            "If the transcripts contain sensitive content, try a smaller session."
        )

    markdown = "".join(
        b.text for b in message.content if getattr(b, "type", None) == "text"
    ).strip()
    if not markdown:
        raise SynthesisError("The model returned an empty document. Try regenerating.")

    save_doc(session_id, markdown)
    _mark_generated(session_id)
    return {
        "session_id": session_id,
        "markdown": markdown,
        "generated_at": datetime.now().strftime(orchestrator.TIME_FMT),
        "served_by": getattr(message, "model", MODEL),
    }
