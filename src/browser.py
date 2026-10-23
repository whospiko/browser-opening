from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from app_log import get_logger
from config import AppConfig
from monitors import Monitor, list_monitors, require_monitor
from paths import profiles_dir, shared_profile_dir


def _sanitize_role(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower()).strip("-_")
    return cleaned or "screen"


def _legacy_profile_candidates() -> list[Path]:
    root = profiles_dir()
    if not root.is_dir():
        return []
    preferred: list[Path] = []
    others: list[Path] = []
    for path in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_dir() or path.name == "shared":
            continue
        if path.name == "cashier":
            preferred.append(path)
        else:
            others.append(path)
    return preferred + others


def ensure_shared_profile() -> Path:
    """Return the shared Chromium profile, migrating a legacy per-role folder once."""
    log = get_logger()
    shared = shared_profile_dir()
    if shared.exists():
        return shared
    root = profiles_dir()
    root.mkdir(parents=True, exist_ok=True)
    for candidate in _legacy_profile_candidates():
        try:
            nonempty = any(candidate.iterdir())
        except OSError:
            nonempty = False
        if not nonempty:
            continue
        try:
            candidate.rename(shared)
        except OSError:
            try:
                shutil.move(str(candidate), str(shared))
            except OSError as exc:
                log.info("Could not migrate profile %s: %s", candidate.name, exc)
                continue
        log.info("Migrated browser profile %s -> shared", candidate.name)
        return shared
    shared.mkdir(parents=True, exist_ok=True)
    log.info("Created shared browser profile at %s", shared)
    return shared

LINUX_EDGE = (
    "microsoft-edge-stable",
    "microsoft-edge",
    "microsoft-edge-beta",
    "microsoft-edge-dev",
)
LINUX_CHROME = (
    "google-chrome-stable",
    "google-chrome",
    "chromium",
    "chromium-browser",
)
LINUX_BRAVE = (
    "brave-browser",
    "brave",
    "brave-browser-stable",
    "brave-browser-beta",
)

WIN_EDGE = (
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Microsoft"
    / "Edge"
    / "Application"
    / "msedge.exe",
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Microsoft"
    / "Edge"
    / "Application"
    / "msedge.exe",
)
WIN_CHROME = (
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Google"
    / "Chrome"
    / "Application"
    / "chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Google"
    / "Chrome"
    / "Application"
    / "chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
)
WIN_BRAVE = (
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "BraveSoftware"
    / "Brave-Browser"
    / "Application"
    / "brave.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "BraveSoftware"
    / "Brave-Browser"
    / "Application"
    / "brave.exe",
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "BraveSoftware"
    / "Brave-Browser"
    / "Application"
    / "brave.exe",
)


class BrowserNotFoundError(RuntimeError):
    pass


def _which_named(names: tuple[str, ...]) -> Path | None:
    extra_dirs = [
        Path("/usr/bin"),
        Path("/usr/local/bin"),
        Path("/opt/google/chrome"),
        Path("/opt/brave.com/brave"),
        Path("/usr/lib/brave-bin"),
    ]
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
        for directory in extra_dirs:
            posix = directory / name
            if posix.exists() and os.access(posix, os.X_OK):
                return posix
    return None


def find_browser(kind: str) -> Path:
    kind = kind.lower().strip()
    if sys.platform == "win32":
        win_map = {"edge": WIN_EDGE, "chrome": WIN_CHROME, "brave": WIN_BRAVE}
        for path in win_map.get(kind, ()):
            if path and path.exists():
                return path
        raise BrowserNotFoundError(_missing_message(kind))
    linux_map = {"edge": LINUX_EDGE, "chrome": LINUX_CHROME, "brave": LINUX_BRAVE}
    found = _which_named(linux_map.get(kind, ()))
    if found:
        return found
    raise BrowserNotFoundError(_missing_message(kind))


def _missing_message(kind: str) -> str:
    if kind == "edge":
        return (
            "Microsoft Edge was not found. On Arch/Omarchy install "
            "`microsoft-edge-stable` from the AUR, or choose Chrome or Brave."
        )
    if kind == "brave":
        return (
            "Brave was not found. On Arch/Omarchy install `brave-bin` from the AUR "
            "(`omarchy pkg aur add brave-bin`)."
        )
    return (
        "Google Chrome / Chromium was not found. On Arch/Omarchy install "
        "`chromium` or `google-chrome`."
    )


def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


def _use_hyprland() -> bool:
    if sys.platform == "win32":
        return False
    try:
        import hyprland
    except ImportError:
        return False
    return hyprland.available()


def _launch_args(
    binary: Path,
    url: str,
    profile: Path,
    role: str,
    monitor: Monitor,
    window_mode: str,
    place_with_hyprland: bool,
) -> list[str]:
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        str(binary),
        f"--user-data-dir={profile}",
        f"--class=pos-{role}",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        "--disable-infobars",
        "--disable-features=Translate,TranslateUI",
    ]
    if place_with_hyprland:
        args.extend(["--ozone-platform=wayland", "--ozone-platform-hint=wayland"])
    elif sys.platform.startswith("linux") and _is_wayland():
        args.extend(
            [
                "--ozone-platform-hint=auto",
                f"--window-position={monitor.x},{monitor.y}",
                f"--window-size={monitor.width},{monitor.height}",
            ]
        )
    else:
        args.extend(
            [
                f"--window-position={monitor.x},{monitor.y}",
                f"--window-size={monitor.width},{monitor.height}",
            ]
        )
    if window_mode == "fullscreen":
        args.append("--kiosk")
    else:
        args.append("--start-maximized")
    args.append(url)
    return args


def launch_role(
    cfg: AppConfig, role: str, url: str, monitor_index: int, window_mode: str
) -> subprocess.Popen:
    log = get_logger()
    monitors = list_monitors()
    monitor = require_monitor(monitors, monitor_index, role)
    binary = find_browser(cfg.browser)
    profile = ensure_shared_profile()
    hypr = _use_hyprland()
    log.info("Launching screen %s (shared profile)", role)
    before_addresses: set[str] = set()
    if hypr and monitor.name:
        import hyprland

        before_addresses = hyprland.client_addresses()
        hyprland.focus_monitor(monitor.name)
        time.sleep(0.15)
    args = _launch_args(binary, url, profile, role, monitor, window_mode, hypr)
    proc = subprocess.Popen(args, close_fds=True)
    if hypr and monitor.name:
        import hyprland

        client = hyprland.wait_for_new_window(
            before_addresses,
            pid=proc.pid,
            class_name=f"pos-{role}",
        )
        if client is None:
            client = hyprland.wait_for_window(proc.pid, class_name=f"pos-{role}")
        if client is None:
            raise RuntimeError(
                f"Opened {role} in the browser, but Hyprland never showed the window. "
                "Check that Chromium is allowed to run on Wayland."
            )
        hyprland.place_window(client, monitor.name, window_mode)
        time.sleep(0.1)
        hyprland.place_window(client, monitor.name, window_mode)
        window_pid = int(client.get("pid") or proc.pid)
        address = str(client.get("address") or "")
        log.info("Placed %s (pid=%s address=%s)", role, window_pid, address or "?")
    else:
        log.info("Started %s (pid=%s)", role, proc.pid)
    return proc


def launch_screens(cfg: AppConfig) -> None:
    log = get_logger()
    errors = cfg.validate()
    if errors:
        raise RuntimeError("\n".join(errors))
    binary = find_browser(cfg.browser)
    names = ", ".join(
        (screen.name.strip() or f"screen-{index}")
        for index, screen in enumerate(cfg.screens, start=1)
    )
    delay = max(0.0, float(cfg.open_delay_seconds))
    log.info(
        "Launching %d screen(s) (%s) with %s (%s); delay between screens=%.2fs",
        len(cfg.screens),
        names or "none",
        cfg.browser,
        binary,
        delay,
    )
    used_roles: set[str] = set()
    for index, screen in enumerate(cfg.screens):
        if index and delay:
            time.sleep(delay)
        role = _sanitize_role(screen.name)
        base = role
        suffix = 2
        while role in used_roles:
            role = f"{base}-{suffix}"
            suffix += 1
        used_roles.add(role)
        launch_role(
            cfg,
            role,
            screen.url.strip(),
            screen.monitor,
            screen.window_mode,
        )
    log.info("All screens launched")


# Back-compat alias for any external callers.
launch_both = launch_screens
