# PyInstaller build recipe for LabScribe.
# Build with:  .venv\Scripts\pyinstaller labscribe.spec --noconfirm
# Output:      dist\LabScribe\LabScribe.exe   (one-folder build)

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ["src\\labscribe\\app.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        # (source, destination inside the bundle) — resource_path() looks these up
        ("src\\labscribe\\dashboard\\static", "dashboard\\static"),
        ("assets\\icon.png", "assets"),
    ],
    hiddenimports=(
        # uvicorn picks its event loop / protocol classes by string at runtime,
        # so PyInstaller's static analysis misses them without this
        collect_submodules("uvicorn")
        # pywebview's Windows backend (WebView2 via .NET) is loaded dynamically
        + ["webview.platforms.edgechromium", "webview.platforms.winforms"]
        # pystray's Windows backend, also chosen at runtime
        + ["pystray._win32"]
    ),
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # one-folder build: binaries live next to the exe
    name="LabScribe",
    icon="assets\\icon.ico",
    console=False,           # GUI app — no terminal window
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="LabScribe",
)
