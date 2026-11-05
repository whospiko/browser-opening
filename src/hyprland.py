from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


def available() -> bool:
    return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) and shutil.which("hyprctl") is not None


def version() -> tuple[int, int, int]:
    try:
        text = subprocess.check_output(["hyprctl", "version"], text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return (0, 0, 0)
    match = re.search(r"Hyprland\s+(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))


def uses_lua_dispatch() -> bool:
    major, minor, _patch = version()
    return (major, minor) >= (0, 55)


def _run_hyprctl(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["hyprctl", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def eval_lua(code: str) -> None:
    completed = _run_hyprctl(["eval", code])
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(detail or "hyprctl eval failed")


def list_monitor_dicts() -> list[dict[str, Any]]:
    completed = _run_hyprctl(["-j", "monitors"])
    if completed.returncode != 0 or not completed.stdout.strip():
        raise RuntimeError((completed.stderr or completed.stdout or "hyprctl monitors failed").strip())
    raw = json.loads(completed.stdout)
    if not isinstance(raw, list):
        raise RuntimeError("hyprctl monitors returned unexpected JSON.")
    monitors: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or item.get("disabled"):
            continue
        monitors.append(
            {
                "x": int(item.get("x") or 0),
                "y": int(item.get("y") or 0),
                "width": int(item.get("width") or 0),
                "height": int(item.get("height") or 0),
                "name": str(item.get("name") or ""),
                "is_primary": bool(item.get("focused")),
            }
        )
    monitors.sort(key=lambda m: (m["x"], m["y"], m["name"]))
    if monitors and not any(m["is_primary"] for m in monitors):
        monitors[0]["is_primary"] = True
    return monitors


def list_clients() -> list[dict[str, Any]]:
    completed = _run_hyprctl(["-j", "clients"])
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    try:
        clients = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(clients, list):
        return []
    return [c for c in clients if isinstance(c, dict)]


def client_addresses(clients: list[dict[str, Any]] | None = None) -> set[str]:
    items = clients if clients is not None else list_clients()
    addresses: set[str] = set()
    for client in items:
        address = str(client.get("address") or "").strip()
        if address:
            addresses.add(address)
    return addresses


def wait_for_window(
    pid: int, class_name: str | None = None, timeout: float = 12.0
) -> dict[str, Any] | None:
    deadline = time.time() + timeout
    wanted = {pid, *_descendant_pids(pid)}
    while time.time() < deadline:
        clients = list_clients()
        by_pid = None
        by_class = None
        for client in clients:
            if int(client.get("pid") or 0) in wanted:
                by_pid = client
            class_value = str(client.get("class") or "")
            if class_name and class_value == class_name:
                by_class = client
        if by_pid is not None:
            return by_pid
        if by_class is not None:
            return by_class
        wanted.update(_descendant_pids(pid))
        time.sleep(0.15)
    return None


def wait_for_new_window(
    before_addresses: set[str],
    *,
    pid: int | None = None,
    class_name: str | None = None,
    timeout: float = 12.0,
) -> dict[str, Any] | None:
    """Wait for a client whose address was not in before_addresses.

    Falls back to pid/class matching when Chromium reuses an address set or
    the new window is slow to appear in the client list.
    """
    deadline = time.time() + timeout
    wanted: set[int] = set()
    if pid is not None:
        wanted = {pid, *_descendant_pids(pid)}
    while time.time() < deadline:
        clients = list_clients()
        for client in clients:
            address = str(client.get("address") or "").strip()
            if address and address not in before_addresses:
                return client
        if wanted:
            for client in clients:
                if int(client.get("pid") or 0) in wanted:
                    address = str(client.get("address") or "").strip()
                    if address and address not in before_addresses:
                        return client
                    if not address:
                        return client
            for client in clients:
                class_value = str(client.get("class") or "")
                if class_name and class_value == class_name:
                    address = str(client.get("address") or "").strip()
                    if address and address not in before_addresses:
                        return client
            wanted.update(_descendant_pids(pid) if pid is not None else set())
        elif class_name:
            for client in clients:
                if str(client.get("class") or "") == class_name:
                    address = str(client.get("address") or "").strip()
                    if address and address not in before_addresses:
                        return client
        time.sleep(0.15)
    return None


def _descendant_pids(root: int) -> set[int]:
    found = {root}
    proc = Path("/proc")
    if not proc.is_dir():
        return found
    changed = True
    while changed:
        changed = False
        try:
            entries = list(proc.iterdir())
        except OSError:
            break
        for entry in entries:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid in found:
                continue
            try:
                status = (entry / "status").read_text(encoding="utf-8")
            except OSError:
                continue
            ppid = None
            for line in status.splitlines():
                if line.startswith("PPid:"):
                    ppid = int(line.split()[1])
                    break
            if ppid in found:
                found.add(pid)
                changed = True
    return found


def _window_selector(client_or_pid: dict[str, Any] | int) -> str:
    if isinstance(client_or_pid, dict):
        address = str(client_or_pid.get("address") or "").strip()
        if address:
            return f"address:{address}"
        pid = int(client_or_pid.get("pid") or 0)
        return f"pid:{pid}"
    return f"pid:{int(client_or_pid)}"


def place_window(
    client_or_pid: dict[str, Any] | int,
    monitor_name: str,
    window_mode: str = "fullscreen",
) -> None:
    selector = _window_selector(client_or_pid)
    maximize = window_mode != "kiosk"
    # Hyprland: 1 = maximized (keeps decorations), 2 = true fullscreen.
    # Client 0 keeps Chromium's title bar (close / minimize) in maximized mode.
    internal = 1 if maximize else 2
    client = 0 if maximize else 2
    if uses_lua_dispatch():
        mon = monitor_name.replace("\\", "\\\\").replace('"', '\\"')
        eval_lua(
            "hl.dispatch(hl.dsp.window.move({"
            f'  monitor = "{mon}", window = "{selector}", follow = false'
            "}))"
        )
        if maximize:
            eval_lua(
                "hl.dispatch(hl.dsp.window.fullscreen_state({"
                f'  internal = {internal}, client = {client}, action = "set", '
                f'window = "{selector}"'
                "}))"
            )
        else:
            eval_lua(
                "hl.dispatch(hl.dsp.window.fullscreen({"
                f'  mode = "fullscreen", action = "set", window = "{selector}"'
                "}))"
            )
        return
    _run_hyprctl(["dispatch", f"movewindow mon:{monitor_name},{selector}"])
    _run_hyprctl(["dispatch", f"fullscreenstate {internal} {client},{selector}"])


def float_and_center(pid: int, monitor_name: str | None = None) -> None:
    selector = f"pid:{pid}"
    if uses_lua_dispatch():
        if monitor_name:
            mon = monitor_name.replace("\\", "\\\\").replace('"', '\\"')
            eval_lua(
                "hl.dispatch(hl.dsp.window.move({"
                f'  monitor = "{mon}", window = "{selector}", follow = false'
                "}))"
            )
        eval_lua(
            "hl.dispatch(hl.dsp.window.float({"
            f'  action = "set", window = "{selector}"'
            "}))"
        )
        eval_lua(f'hl.dispatch(hl.dsp.window.center({{ window = "{selector}" }}))')
        return
    if monitor_name:
        _run_hyprctl(["dispatch", f"movewindow mon:{monitor_name},{selector}"])
    _run_hyprctl(["dispatch", f"setfloating 1,{selector}"])
    _run_hyprctl(["dispatch", f"centerwindow,{selector}"])


def focus_monitor(monitor_name: str) -> None:
    if uses_lua_dispatch():
        mon = monitor_name.replace("\\", "\\\\").replace('"', '\\"')
        eval_lua(f'hl.dispatch(hl.dsp.focus({{ monitor = "{mon}" }}))')
        return
    _run_hyprctl(["dispatch", f"focusmonitor {monitor_name}"])


def focus_window(client_or_pid: dict[str, Any] | int | str) -> None:
    """Focus an existing client so Chromium opens the next URL as a tab there."""
    if isinstance(client_or_pid, str):
        address = client_or_pid.strip()
        selector = f"address:{address}" if address else ""
    else:
        selector = _window_selector(client_or_pid)
    if not selector:
        return
    # Classic dispatch works on all Hyprland versions; address:/pid: selectors.
    _run_hyprctl(["dispatch", f"focuswindow {selector}"])


def reload() -> None:
    _run_hyprctl(["reload"])


def config_errors() -> str:
    completed = _run_hyprctl(["configerrors"])
    return (completed.stdout or "").strip()


def autostart_lua_path() -> Path:
    return Path.home() / ".config" / "hypr" / "autostart.lua"
