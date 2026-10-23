from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from app_log import get_logger, log_exception
from paths import launcher_path

LINUX_DESKTOP_NAME = "browser-tool.desktop"
WIN_LNK_NAME = "Browser-Tool.lnk"
HYPR_BEGIN = "-- BROWSER-TOOL BEGIN"
HYPR_END = "-- BROWSER-TOOL END"


def _linux_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / LINUX_DESKTOP_NAME


def _windows_startup_dir() -> Path:
    appdata = Path.home() / "AppData" / "Roaming"
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _windows_lnk_path() -> Path:
    return _windows_startup_dir() / WIN_LNK_NAME


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _desktop_quote(value: str) -> str:
    return '"' + value.replace('"', r"\"") + '"'


def _hypr_config_dir() -> Path:
    return Path.home() / ".config" / "hypr"


def _hypr_autostart_path() -> Path:
    return _hypr_config_dir() / "autostart.lua"


def _uses_omarchy() -> bool:
    return Path("/usr/share/omarchy").is_dir() or shutil.which("omarchy") is not None


def is_enabled() -> bool:
    if sys.platform == "win32":
        startup = _windows_startup_dir()
        return _windows_lnk_path().exists() or (startup / "POS-Browser-Launcher.lnk").exists()
    if _linux_desktop_path().exists():
        return True
    if (Path.home() / ".config" / "autostart" / "pos-browser-launcher.desktop").exists():
        return True
    path = _hypr_autostart_path()
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return HYPR_BEGIN in text or "-- POS-BROWSER-LAUNCHER BEGIN" in text


def enable() -> Path:
    log = get_logger()
    target = launcher_path()
    log.info("Enabling autostart for %s", target)
    if sys.platform == "win32":
        path = _enable_windows(target)
        log.info("Autostart shortcut written: %s", path)
        return path
    desktop = _enable_linux_xdg(target)
    log.info("Autostart desktop entry written: %s", desktop)
    if _hypr_config_dir().is_dir() or os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        hypr_path = _enable_hyprland(target)
        log.info("Hyprland autostart block updated: %s", hypr_path)
    return desktop


def disable() -> None:
    log = get_logger()
    log.info("Disabling autostart")
    if sys.platform == "win32":
        for name in (WIN_LNK_NAME, "POS-Browser-Launcher.lnk"):
            path = _windows_startup_dir() / name
            if path.exists():
                path.unlink()
                log.info("Removed Startup shortcut: %s", path)
        return
    for name in (LINUX_DESKTOP_NAME, "pos-browser-launcher.desktop"):
        path = Path.home() / ".config" / "autostart" / name
        if path.exists():
            path.unlink()
            log.info("Removed desktop autostart: %s", path)
    _disable_hyprland()


def apply(open_on_startup: bool) -> None:
    try:
        if open_on_startup:
            enable()
        else:
            disable()
    except Exception as exc:
        log_exception("Autostart update failed", exc)
        raise


def _enable_linux_xdg(target: Path) -> Path:
    desktop = _linux_desktop_path()
    desktop.parent.mkdir(parents=True, exist_ok=True)
    exec_path = target.resolve()
    quoted_bin = _desktop_quote(str(exec_path))
    exec_line = f"uwsm-app -- {quoted_bin}" if shutil.which("uwsm-app") else quoted_bin
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Browser Tool\n"
        "Comment=Open dual-screen POS browsers\n"
        f"Exec={exec_line}\n"
        f"Path={_desktop_quote(str(exec_path.parent))}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-Hyprland-Autostart=true\n"
    )
    desktop.write_text(content, encoding="utf-8")
    desktop.chmod(0o644)
    return desktop


def _hypr_exec_line(target: Path) -> str:
    command = shlex.quote(str(target.resolve()))
    if shutil.which("uwsm-app"):
        command = f"uwsm-app -- {command}"
    if _uses_omarchy():
        return f"o.exec_on_start({_lua_string(command)})"
    return (
        "hl.on(\"hyprland.start\", function()\n"
        f"  hl.exec_cmd({_lua_string(command)})\n"
        "end)"
    )


def _lua_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _replace_hypr_block(existing: str, inner: str | None) -> str:
    pattern = re.compile(
        re.escape(HYPR_BEGIN) + r".*?" + re.escape(HYPR_END) + r"\n?",
        re.DOTALL,
    )
    stripped = pattern.sub("", existing).rstrip() + "\n"
    if inner is None:
        return stripped if stripped.strip() else stripped
    block = f"{HYPR_BEGIN}\n{inner.rstrip()}\n{HYPR_END}\n"
    if not stripped.strip():
        stripped = (
            "-- Extra autostart processes.\n"
            '-- o.launch_on_start("my-service")\n'
        )
    return stripped.rstrip() + "\n\n" + block


def _enable_hyprland(target: Path) -> Path:
    path = _hypr_autostart_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(_replace_hypr_block(existing, _hypr_exec_line(target)), encoding="utf-8")
    _reload_hyprland()
    return path


def _disable_hyprland() -> None:
    path = _hypr_autostart_path()
    if not path.exists():
        return
    existing = path.read_text(encoding="utf-8")
    legacy_begin = "-- POS-BROWSER-LAUNCHER BEGIN"
    legacy_end = "-- POS-BROWSER-LAUNCHER END"
    if HYPR_BEGIN not in existing and legacy_begin not in existing:
        return
    updated = _replace_hypr_block(existing, None)
    if legacy_begin in updated:
        pattern = re.compile(
            re.escape(legacy_begin) + r".*?" + re.escape(legacy_end) + r"\n?",
            re.DOTALL,
        )
        updated = pattern.sub("", updated)
    path.write_text(updated, encoding="utf-8")
    _reload_hyprland()


def _reload_hyprland() -> None:
    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") or not shutil.which("hyprctl"):
        return
    try:
        import hyprland

        hyprland.reload()
        errors = hyprland.config_errors()
    except Exception:
        return
    if errors and "no errors" not in errors.lower():
        raise RuntimeError(f"Hyprland rejected autostart.lua:\n{errors}")


def _enable_windows(target: Path) -> Path:
    lnk = _windows_lnk_path()
    lnk.parent.mkdir(parents=True, exist_ok=True)
    target_s = str(target.resolve()) if target.exists() else str(target)
    workdir = str(target.parent)
    script = (
        "$WshShell = New-Object -ComObject WScript.Shell\n"
        f"$Shortcut = $WshShell.CreateShortcut({_ps_quote(str(lnk))})\n"
        f"$Shortcut.TargetPath = {_ps_quote(target_s)}\n"
        f"$Shortcut.WorkingDirectory = {_ps_quote(workdir)}\n"
        "$Shortcut.WindowStyle = 1\n"
        '$Shortcut.Description = "Browser Tool — open dual-screen POS browsers"\n'
        "$Shortcut.Save()\n"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"Could not create Windows Startup shortcut.\n{detail}")
    return lnk
