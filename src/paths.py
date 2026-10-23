from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

APP_NAME = "POSBrowserLauncher"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return app_dir() / "config.json"


def example_config_path() -> Path:
    return app_dir() / "config.example.json"


def _data_root() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    xdg = os.environ.get("XDG_DATA_HOME")
    return Path(xdg) if xdg else Path.home() / ".local" / "share"


def profiles_dir() -> Path:
    return _data_root() / APP_NAME / "profiles"


def shared_profile_dir() -> Path:
    """Single Chromium user-data-dir shared by every screen (same localStorage)."""
    return profiles_dir() / "shared"


def logs_dir() -> Path:
    return app_dir() / "log"


def log_path() -> Path:
    """Today's log file: YYYYDDMM.log (year, day, month), e.g. 20262210.log."""
    return logs_dir() / f"{datetime.now().strftime('%Y%d%m')}.log"


def launcher_path() -> Path:
    """Path the OS should start at login (packaged binary, else run script)."""
    directory = app_dir()
    if sys.platform == "win32":
        packaged = directory / "browser-tool.exe"
        if is_frozen() or packaged.exists():
            return packaged
        return directory / "open.bat"
    packaged = directory / "browser-tool"
    if is_frozen() or packaged.exists():
        return packaged
    return directory / "open.sh"
