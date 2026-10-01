"""Audit release files and optionally create the portable archive."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import struct
import zipfile


ROOT = Path(__file__).resolve().parent.parent
ASSETS = runpy.run_path(str(ROOT / "packaging/bundle_assets.py"))
FORBIDDEN_PARTS = {"obsidian", ".study-data", ".study-app", ".study_app", ".git", "node_modules", "uploads"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(bundle):
    bundle = bundle.resolve(strict=True)
    executable = bundle / "ShizhiStudyAssistant.exe"
    data = executable.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("Missing Windows executable")
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[offset:offset+4] != b"PE\0\0" or struct.unpack_from("<H", data, offset+4)[0] != 0x8664:
        raise ValueError("The executable must be Windows x64")
    actual = set()
    for path in bundle.rglob("*"):
        relative = path.relative_to(bundle)
        if path.is_symlink() or not path.resolve().is_relative_to(bundle):
            raise ValueError(f"Link in release bundle: {relative}")
        if any(part.lower() in FORBIDDEN_PARTS or part.lower().startswith(".env") for part in relative.parts):
            raise ValueError(f"Private directory/configuration in release: {relative}")
        if path.is_file() and path.suffix.lower() in (".sqlite", ".sqlite3", ".db", ".log", ".pem", ".key"):
            raise ValueError(f"Runtime state or secret in release: {relative}")
        if path.is_file() and relative.parts[:2] == ("_internal", "web"):
            actual.add(Path(*relative.parts[2:]).as_posix())
    if actual != set(ASSETS["WEB_FILES"]):
        raise ValueError(f"Web allowlist mismatch: missing={sorted(set(ASSETS['WEB_FILES'])-actual)}, unexpected={sorted(actual-set(ASSETS['WEB_FILES']))}")
    for filename in ASSETS["WEB_FILES"]:
        if digest(bundle / "_internal/web" / filename) != digest(ROOT / "web" / filename):
            raise ValueError(f"Web asset changed during bundling: {filename}")
    for filename in ASSETS["GENERATED_LICENSES"]:
        if digest(bundle / "_internal/licenses" / filename) != digest(ROOT / "build/windows/generated/licenses" / filename):
            raise ValueError(f"License mismatch: {filename}")
    if digest(bundle / "_internal/THIRD_PARTY_NOTICES.md") != digest(ROOT / "THIRD_PARTY_NOTICES.md"):
        raise ValueError("Missing third-party notices")
    if digest(bundle / "_internal/app.ico") != digest(ROOT / "build/windows/generated/app.ico"):
        raise ValueError("Missing application icon")
    info = json.loads((bundle / "_internal/build-info.json").read_text(encoding="utf-8"))
    version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    if info["version"] != version:
        raise ValueError("Bundle version does not match package.json")
    print(f"Audited Windows x64 bundle: {version}, {len(actual)} allowlisted web assets, no user vault/database/configuration")
    return bundle


def create_zip(bundle, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                name = f"{bundle.name}/{path.relative_to(bundle).as_posix()}"
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o100755 if path.suffix.lower() == ".exe" else 0o100644) << 16
                archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(output) as archive:
        corrupt = archive.testzip()
        if corrupt:
            raise ValueError(f"Corrupt portable archive entry: {corrupt}")
        expected = {f"{bundle.name}/{path.relative_to(bundle).as_posix()}" for path in bundle.rglob("*") if path.is_file()}
        if set(archive.namelist()) != expected:
            raise ValueError("Portable archive does not match the audited bundle")
    print(f"Created and verified {output.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--create-zip", type=Path)
    arguments = parser.parse_args()
    checked = verify(arguments.bundle)
    if arguments.create_zip:
        create_zip(checked, arguments.create_zip.resolve())
