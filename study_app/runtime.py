"""Keep bundled read-only assets separate from each user's writable study data."""
from __future__ import annotations

import os
from pathlib import Path
import sys


APP_DIRECTORY = "ShizhiStudyAssistant"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    # PyInstaller extracts one-file assets here, and uses _internal for onedir.
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return source_root()


def user_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local).resolve() / APP_DIRECTORY
    if os.name == "nt":
        return Path.home() / "AppData" / "Local" / APP_DIRECTORY
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_DIRECTORY


def default_data_dir() -> Path:
    explicit = os.environ.get("STUDY_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return user_root() / "data" if is_frozen() else source_root() / ".study-data"


def default_vault() -> Path:
    explicit = os.environ.get("STUDY_VAULT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return user_root() / "vault" if is_frozen() else source_root() / "obsidian" / "universities study program"
