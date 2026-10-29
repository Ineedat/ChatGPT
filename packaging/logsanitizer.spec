# Build from the repository root with: python -m PyInstaller --clean --noconfirm packaging/logsanitizer.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path.cwd()
frontend_dist = ROOT / "frontend" / "dist"
if not (frontend_dist / "index.html").is_file():
    raise RuntimeError("Build the React frontend first: npm run build in frontend/")

a = Analysis(
    [str(ROOT / "backend" / "src" / "logsanitizer" / "__main__.py")],
    pathex=[str(ROOT / "backend" / "src")],
    binaries=[],
    datas=[
        (str(frontend_dist), "frontend/dist"),
        (str(ROOT / "config" / "deployment.example.json"), "config"),
        (str(ROOT / "docs"), "docs"),
    ],
    hiddenimports=collect_submodules("ldap3"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LogSanitizer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LogSanitizer",
)
