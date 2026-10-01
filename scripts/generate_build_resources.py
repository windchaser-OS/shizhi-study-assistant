"""Generate the existing leaf emblem, version resource and release notices."""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tkinter

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "build/windows/generated"


def bezier(start, first, second, end, steps=32):
    return [
        tuple((1-t)**3*start[axis] + 3*(1-t)**2*t*first[axis]
              + 3*(1-t)*t*t*second[axis] + t**3*end[axis] for axis in (0, 1))
        for t in (i / steps for i in range(steps + 1))
    ]


def make_icon():
    # Faithfully redraw the two cubic curves in the first leaf of favicon.svg;
    # the other three leaves are quarter-turns around the emblem's centre.
    image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = 16
    draw.rounded_rectangle((0, 0, 1023, 1023), radius=17*scale, fill="#f1f3e9")
    leaf = bezier((30, 30), (13, 32), (10, 16), (14, 12))
    leaf += bezier((14, 12), (27, 10), (33, 18), (30, 30))
    for rotation in range(4):
        points = []
        for x, y in leaf:
            x, y = x - 32, y - 32
            for _ in range(rotation):
                x, y = -y, x
            points.append(((x + 32) * scale, (y + 32) * scale))
        draw.polygon(points, fill="#365b47")
    image = image.resize((256, 256), Image.Resampling.LANCZOS)
    image.save(OUTPUT / "app.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])


def copy_distribution_license(package, filename):
    distribution = importlib.metadata.distribution(package)
    candidates = [file for file in distribution.files or ()
                  if Path(str(file)).name.upper() in ("LICENSE", "LICENSE.TXT", "COPYING.TXT")]
    if not candidates:
        raise RuntimeError(f"Cannot find the installed {package} license")
    shutil.copyfile(distribution.locate_file(candidates[0]), OUTPUT / "licenses" / filename)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "licenses").mkdir(exist_ok=True)
    version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("Windows release requires a version like 1.0.0")
    version_tuple = tuple(int(part) for part in parts) + (0,)
    make_icon()
    strings = {
        "CompanyName": "Shizhi Study Assistant",
        "FileDescription": "拾知学习空间",
        "FileVersion": version,
        "InternalName": "ShizhiStudyAssistant",
        "OriginalFilename": "ShizhiStudyAssistant.exe",
        "ProductName": "拾知学习空间",
        "ProductVersion": version,
    }
    resource = "VSVersionInfo(\n"
    resource += f"  ffi=FixedFileInfo(filevers={version_tuple!r}, prodvers={version_tuple!r}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
    resource += "  kids=[StringFileInfo([StringTable('080404B0', [\n"
    resource += ",\n".join(f"    StringStruct({key!r}, {value!r})" for key, value in strings.items())
    resource += "\n  ])]), VarFileInfo([VarStruct('Translation', [2052, 1200])])]\n)\n"
    (OUTPUT / "version-info.txt").write_text(resource, encoding="utf-8")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("The Python installation must include LICENSE.txt")
    shutil.copyfile(python_license, OUTPUT / "licenses/Python-LICENSE.txt")
    copy_distribution_license("pypdf", "pypdf-LICENSE.txt")
    copy_distribution_license("PyInstaller", "PyInstaller-COPYING.txt")
    tcl_version = tkinter.Tcl().eval("info patchlevel")
    if tcl_version != "8.6.15" or not ssl.OPENSSL_VERSION.startswith("OpenSSL 3.0.16 "):
        raise RuntimeError("Review vendored Tcl/OpenSSL licenses before changing the pinned Python runtime")
    shutil.copyfile(Path(sys.base_prefix) / "tcl/tk8.6/license.terms", OUTPUT / "licenses/Tk-LICENSE.txt")
    for filename in ("Tcl-LICENSE.txt", "OpenSSL-LICENSE.txt", "Expat-LICENSE.txt", "zlib-LICENSE.txt"):
        shutil.copyfile(ROOT / "packaging/licenses" / filename, OUTPUT / "licenses" / filename)
    shutil.copyfile(ROOT / "web/vendor/katex/LICENSE", OUTPUT / "licenses/KaTeX-LICENSE.txt")
    packages = {name: importlib.metadata.version(name) for name in
                ("pypdf", "PyInstaller", "pyinstaller-hooks-contrib", "Pillow",
                 "altgraph", "packaging", "pefile", "pywin32-ctypes", "setuptools")}
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
    info = {
        "application": "ShizhiStudyAssistant", "version": version,
        "python": sys.version.split()[0], "architecture": "windows-x64",
        "dependencies": packages, "openssl": ssl.OPENSSL_VERSION, "tcl": tcl_version,
        "source_commit": revision.stdout.strip() if revision.returncode == 0 else None,
        "source_dirty": bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
    }
    (OUTPUT / "build-info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated release resources for {version}")


if __name__ == "__main__":
    main()
