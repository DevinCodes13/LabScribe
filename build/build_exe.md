# Building & running LabScribe

## One-time setup (already done on this machine)

```powershell
cd "C:\Claude Code Projects\Lab Scribe"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe build\make_icon.py   # regenerates assets/icon.png + .ico
```

## Build the .exe

```powershell
cd "C:\Claude Code Projects\Lab Scribe"
.\.venv\Scripts\pyinstaller.exe labscribe.spec --noconfirm --workpath build\pyinstaller --distpath dist
```

Output: `dist\LabScribe\LabScribe.exe` (one-folder build — the whole
`dist\LabScribe` folder is the app; the exe won't run if moved out alone).
Pin the exe to the taskbar / make a shortcut as you like.

## Run from source (development)

```powershell
# Full app: window + tray
.\.venv\Scripts\python.exe src\labscribe\app.py

# API + dashboard only, in a normal browser at http://127.0.0.1:8471
.\.venv\Scripts\python.exe src\labscribe\app.py --server-only
```

## Where things live at runtime

| Mode | Settings (.env) | Log file |
|---|---|---|
| Packaged .exe | `%APPDATA%\LabScribe\.env` | `%APPDATA%\LabScribe\labscribe.log` |
| From source | `<repo>\.env` (gitignored) | console output |

## Runtime notes (M6)

- **First run**: with no settings yet, the app opens a setup wizard. To re-trigger
  it for testing, delete `%APPDATA%\LabScribe\.env` (packaged) or `<repo>\.env` (dev).
- **Single instance**: a fixed loopback port (49517) is bound as a lock. A second
  launch finds it taken, shows a "already running" dialog, and exits. Nothing to
  clean up — the OS frees the port on exit.
- **WebView2**: the app renders via the Microsoft Edge WebView2 runtime (present on
  current Windows 10/11). If it's missing, startup shows a dialog pointing to the
  installer and logs details to `%APPDATA%\LabScribe\labscribe.log`.

## Gotchas learned during M1

- **Windowed exes have no stdout/stderr.** uvicorn logs to stderr; with
  `console=False` that's `None` and the server dies silently. `app.py`
  redirects both to the log file when frozen — don't remove that block.
- uvicorn, pywebview's WebView2 backend, and pystray's win32 backend are
  all loaded dynamically; the `hiddenimports` list in `labscribe.spec`
  is what makes PyInstaller include them.
