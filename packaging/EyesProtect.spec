# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


repo_root = Path(SPECPATH).parent.resolve()
backend_root = repo_root / "backend"
sys.path.insert(0, str(backend_root))

datas = []
frontend_dist = repo_root / "frontend" / "dist"
if frontend_dist.exists():
    datas.append((str(frontend_dist), "frontend/dist"))

desktop_script = repo_root / "desktop_reminder.py"
if desktop_script.exists():
    datas.append((str(desktop_script), "."))

def safe_collect_submodules(package_name):
    try:
        return collect_submodules(package_name)
    except Exception:
        return []


hiddenimports = []
for package_name in (
    "app",
    "uvicorn",
    "fastapi",
    "starlette",
    "pydantic",
    "requests",
):
    hiddenimports.extend(safe_collect_submodules(package_name))

hiddenimports.extend(
    [
        "desktop_reminder",
        "tkinter",
        "tkinter.ttk",
        "sqlite3",
    ]
)


a = Analysis(
    [str(repo_root / "packaged_app.py")],
    pathex=[str(repo_root), str(backend_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EyesProtect",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="EyesProtect",
)
