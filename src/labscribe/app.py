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

M6 polish added here: a single-instance guard (a second launch just focuses the
first and exits), a first-close "still running in the tray" notification, a
working Generate Docs tray action, and a fatal-error message box so startup
failures (e.g. a missing WebView2 runtime) surface instead of vanishing.
"""

import argparse
import os
import socket
import sys
import threading
import time
import traceback
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

# A fixed loopback port used purely as a single-instance lock. Binding it holds
# the lock for the process lifetime; the OS frees it automatically on exit, so
# there's no stale lockfile to clean up after a crash.
_SINGLETON_PORT = 49517
_singleton_socket: socket.socket | None = None


def _message_box(text: str, title: str = APP_NAME) -> None:
    """Show a native dialog (Windows). No-op elsewhere; never raises."""
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)  # MB_ICONINFORMATION
        else:
            print(f"{title}: {text}")
    except Exception:
        pass


def acquire_single_instance() -> bool:
    """Return True if we're the only instance; False if another already holds it."""
    global _singleton_socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # SO_REUSEADDR is deliberately NOT set: we want the second instance's
        # bind to fail while the first is alive.
        s.bind(("127.0.0.1", _SINGLETON_PORT))
        s.listen(1)
        _singleton_socket = s  # keep a reference so it isn't garbage-collected
        return True
    except OSError:
        s.close()
        return False


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

    from labscribe.capture import orchestrator, watcher

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
    # orchestrator/engine directly. Errors surface as a tray notification
    # instead of a crash. The `enabled` callables are re-evaluated by pystray
    # every time the menu opens.
    def tray_start(icon, item):
        try:
            s = orchestrator.start_session()
            watcher.start(s)  # live troubleshooting-moment nudges, see watcher.py
            icon.notify(f"Capture started: {s['name']}", APP_NAME)
        except orchestrator.SessionError as e:
            icon.notify(str(e), APP_NAME)

    def tray_stop(icon, item):
        try:
            s = orchestrator.stop_session()
            watcher.stop()
            c = s["counts"]
            icon.notify(
                f"Stopped: {c['transcripts']} transcripts, "
                f"{c['screenshots']} screenshots, {c['notes']} notes",
                APP_NAME,
            )
        except orchestrator.SessionError as e:
            icon.notify(str(e), APP_NAME)

    def tray_generate(icon, item):
        # Generate for the active session, else the most recent one. The API
        # call can take a minute, so run it off the tray thread.
        from labscribe.synthesis import engine
        target = orchestrator.active_session()
        if target is None:
            sessions = orchestrator.list_sessions()
            target = sessions[0] if sessions else None
        if target is None:
            icon.notify("No sessions yet — start one first.", APP_NAME)
            return
        icon.notify(f"Generating docs for '{target['name']}'…", APP_NAME)

        def work():
            try:
                engine.generate_docs(target["id"])
                icon.notify("Docs generated — open the dashboard to review.", APP_NAME)
            except engine.SynthesisError as e:
                icon.notify(str(e), APP_NAME)
            except Exception:
                icon.notify("Doc generation failed — see labscribe.log.", APP_NAME)

        threading.Thread(target=work, daemon=True, name="labscribe-gen").start()

    def session_active(item) -> bool:
        return orchestrator.active_session() is not None

    menu = pystray.Menu(
        pystray.MenuItem("Show Dashboard", show_dashboard, default=True),
        pystray.MenuItem("Start Session", tray_start,
                         enabled=lambda item: not session_active(item)),
        pystray.MenuItem("Stop Session", tray_stop, enabled=session_active),
        pystray.MenuItem("Generate Docs", tray_generate),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    )
    icon = pystray.Icon(APP_NAME, image, APP_NAME, menu)
    # Wire the watcher's alerts to real tray notifications, regardless of
    # whether the session that triggered it was started from the tray menu
    # or the dashboard button — both call the same orchestrator functions.
    watcher.set_notifier(lambda message: icon.notify(message, APP_NAME))
    return icon


def run_app() -> None:
    """Windowed app: server + native window + tray. Raises on fatal startup error."""
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

    tray = make_tray_icon(window, server)

    # Notify once, the first time the window is closed to the tray, so the app
    # doesn't seem to have vanished.
    notified = {"closed": False}

    def on_closing():
        window.hide()
        if not notified["closed"]:
            notified["closed"] = True
            try:
                tray.notify("LabScribe is still running in the tray. "
                            "Right-click the icon for options or to Quit.", APP_NAME)
            except Exception:
                pass
        return False  # cancels the close

    window.events.closing += on_closing

    tray.run_detached()

    # Blocks until window.destroy() is called from the tray's Quit
    webview.start()

    server.should_exit = True


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

    # Single-instance guard: if another copy is already running, focus is left
    # to it and this launch exits cleanly instead of starting a second tray.
    if not acquire_single_instance():
        _message_box("LabScribe is already running — check the system tray "
                     "(bottom-right of the taskbar).")
        return

    try:
        run_app()
    except Exception:
        tb = traceback.format_exc()
        try:
            (Path(os.environ.get("APPDATA", ".")) / "LabScribe" / "labscribe.log")\
                .open("a", encoding="utf-8").write("\nFATAL:\n" + tb + "\n")
        except Exception:
            pass
        _message_box(
            "LabScribe couldn't start.\n\n"
            "This is often a missing Microsoft Edge WebView2 runtime — install it "
            "from https://developer.microsoft.com/microsoft-edge/webview2/ and try "
            "again.\n\nDetails were written to labscribe.log in %APPDATA%\\LabScribe.",
            APP_NAME + " — startup error",
        )
        raise


if __name__ == "__main__":
    main()
