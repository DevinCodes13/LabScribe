"""LabScribe entry point: local API server + native window + system-tray icon.

Threading model (this is the part worth understanding):

  - MAIN THREAD      pywebview's GUI loop. On Windows the native window MUST
                     own the main thread, so webview.start() runs here and
                     blocks until the app quits.
  - SERVER THREAD    uvicorn serving the FastAPI app on 127.0.0.1:<free port>.
                     Daemon thread — dies automatically with the process.
  - TRAY THREAD      pystray's icon loop, started with run_detached().

Closing the window does NOT exit the app: we intercept the closing event and
hide the window instead, so LabScribe keeps running in the tray (spec §6).
Only the tray menu's Quit actually exits.
"""

import argparse
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

# In a windowed (no-console) exe, stdout/stderr don't exist (None) and any
# library that logs to them — uvicorn does — breaks silently. Point them at
# a log file instead so the app works AND we get diagnostics if it doesn't.
# NOTE: never log secrets; settings.py keeps the API key out of all output.
if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
    _log_dir = Path(os.environ.get("APPDATA", ".")) / "LabScribe"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log = open(_log_dir / "labscribe.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

# Make `import labscribe.*` work when running this file directly from source
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labscribe.api.routes import create_app  # noqa: E402

APP_NAME = "LabScribe"


def resource_path(relative: str) -> Path:
    """Find bundled files both in dev and inside the PyInstaller build."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parents[2] / relative


def find_free_port() -> int:
    """Ask the OS for an unused port so we never collide with other apps."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int) -> "uvicorn.Server":
    import uvicorn

    config = uvicorn.Config(
        create_app(),
        host="127.0.0.1",   # localhost only — never reachable from the network
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="labscribe-api")
    thread.start()
    return server


def wait_for_server(port: int, timeout: float = 15.0) -> None:
    """Block until the API answers, so the window never opens on a dead page."""
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError("LabScribe API server failed to start")


def make_tray_icon(window, server) -> "pystray.Icon":
    import pystray
    from PIL import Image

    from labscribe.capture import orchestrator

    image = Image.open(resource_path("assets/icon.png"))

    def show_dashboard(icon, item):
        window.show()
        window.restore()

    def quit_app(icon, item):
        icon.stop()
        server.should_exit = True
        # Destroying the window unblocks webview.start() on the main thread
        window.destroy()

    # The tray shares the process with the API server, so it can drive the
    # orchestrator directly. Errors (e.g. folder not configured) surface as
    # a tray notification instead of a crash. The `enabled` callables are
    # re-evaluated by pystray every time the menu opens.
    def tray_start(icon, item):
        try:
            s = orchestrator.start_session()
            icon.notify(f"Capture started: {s['name']}", APP_NAME)
        except orchestrator.SessionError as e:
            icon.notify(str(e), APP_NAME)

    def tray_stop(icon, item):
        try:
            s = orchestrator.stop_session()
            c = s["counts"]
            icon.notify(
                f"Stopped: {c['transcripts']} transcripts, "
                f"{c['screenshots']} screenshots, {c['notes']} notes",
                APP_NAME,
            )
        except orchestrator.SessionError as e:
            icon.notify(str(e), APP_NAME)

    def session_active(item) -> bool:
        return orchestrator.active_session() is not None

    menu = pystray.Menu(
        pystray.MenuItem("Show Dashboard", show_dashboard, default=True),
        pystray.MenuItem("Start Session", tray_start,
                         enabled=lambda item: not session_active(item)),
        pystray.MenuItem("Stop Session", tray_stop, enabled=session_active),
        pystray.MenuItem("Generate Docs (M3)", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    )
    return pystray.Icon(APP_NAME, image, APP_NAME, menu)


def main() -> None:
    parser = argparse.ArgumentParser(prog="labscribe")
    parser.add_argument(
        "--server-only",
        action="store_true",
        help="Run only the API server on a fixed port (development/testing).",
    )
    parser.add_argument("--port", type=int, default=8471)
    args = parser.parse_args()

    if args.server_only:
        # Dev mode: no window, no tray — just the API + dashboard in a browser.
        import uvicorn
        uvicorn.run(create_app(), host="127.0.0.1", port=args.port)
        return

    import webview

    port = find_free_port()
    server = start_server(port)
    wait_for_server(port)

    window = webview.create_window(
        APP_NAME,
        f"http://127.0.0.1:{port}/",
        width=1000,
        height=700,
        min_size=(760, 520),
    )

    def on_closing():
        # Hide to tray instead of exiting (spec: app runs quietly in background)
        window.hide()
        return False  # cancels the close

    window.events.closing += on_closing

    tray = make_tray_icon(window, server)
    tray.run_detached()

    # Blocks until window.destroy() is called from the tray's Quit
    webview.start()

    server.should_exit = True


if __name__ == "__main__":
    main()
