# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import runpy

ROOT = Path(SPECPATH).parent.resolve()
GENERATED = ROOT / "build/windows/generated"
asset_helpers = runpy.run_path(str(ROOT / "packaging/bundle_assets.py"))
assets = asset_helpers["collect_assets"](ROOT)

a = Analysis(
    [str(ROOT / "scripts/desktop_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=assets,
    hiddenimports=["pypdf", "tkinter", "tkinter.messagebox"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PIL", "pytest", "tkinter.test"],
    noarchive=False,
    optimize=0,
)

# Reject unexpected local Python modules as well as data collection. Installed
# dependencies in the dedicated build venv are permitted, personal directories
# are never import roots or data sources.
for _name, _source, _kind in a.pure + a.scripts:
    _path = Path(_source).resolve()
    if _path.is_relative_to(ROOT):
        _relative = _path.relative_to(ROOT)
        if _relative.parts[0] == "study_app" and _path.suffix == ".py":
            continue
        if _relative.as_posix() == "scripts/desktop_entry.py":
            continue
        if _relative.parts[0] in (".venv-build", ".venv") and "site-packages" in _relative.parts:
            continue
        raise ValueError(f"Unexpected local module in release: {_relative}")

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ShizhiStudyAssistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(GENERATED / "app.ico"),
    version=str(GENERATED / "version-info.txt"),
    contents_directory="_internal",
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=False,
    name="ShizhiStudyAssistant",
)
