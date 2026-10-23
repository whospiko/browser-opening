"""Check GitLab Releases and replace packaged binaries in place."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app_log import get_logger, log_exception
from paths import app_dir, is_frozen
from version import GITLAB_HOST, GITLAB_PROJECT, __version__

USER_AGENT = f"browser-tool-updater/{__version__}"


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    version: str
    download_url: str
    asset_name: str


def parse_version(text: str) -> tuple[int, ...]:
    """Normalize v1.2.3 / 1.2.3-dev into comparable integer tuples."""
    raw = text.strip()
    if raw.lower().startswith("v"):
        raw = raw[1:]
    # Drop pre-release / local suffix for numeric compare
    for sep in ("-", "+", "_"):
        if sep in raw:
            raw = raw.split(sep, 1)[0]
            break
    parts: list[int] = []
    for piece in raw.split("."):
        if not piece.isdigit():
            break
        parts.append(int(piece))
    return tuple(parts) if parts else (0,)


def is_newer(remote: str, current: str) -> bool:
    return parse_version(remote) > parse_version(current)


def _asset_name_for_platform() -> str:
    if sys.platform == "win32":
        return "browser-tool-windows.zip"
    return "browser-tool-linux.tar.gz"


def _binary_names() -> tuple[str, ...]:
    if sys.platform == "win32":
        return ("browser-tool-config.exe", "browser-tool.exe")
    return ("browser-tool-config", "browser-tool")


def _config_binary_name() -> str:
    return "browser-tool-config.exe" if sys.platform == "win32" else "browser-tool-config"


def _api_get(url: str) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def fetch_latest_release() -> ReleaseInfo:
    if not GITLAB_PROJECT or GITLAB_PROJECT == "OWNER/PROJECT":
        raise RuntimeError(
            "GITLAB_PROJECT is not set. Edit src/version.py before shipping builds."
        )
    encoded = urllib.parse.quote(GITLAB_PROJECT, safe="")
    url = f"{GITLAB_HOST}/api/v4/projects/{encoded}/releases/permalink/latest"
    data = _api_get(url)
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected GitLab releases response")
    tag = str(data.get("tag_name") or "").strip()
    if not tag:
        raise RuntimeError("Latest release has no tag_name")
    version = tag[1:] if tag.lower().startswith("v") else tag
    wanted = _asset_name_for_platform()
    download_url = _find_asset_url(data, wanted, version)
    if not download_url:
        raise RuntimeError(f"Release {tag} has no asset named {wanted}")
    return ReleaseInfo(
        tag=tag,
        version=version,
        download_url=download_url,
        asset_name=wanted,
    )


def _find_asset_url(release: dict, asset_name: str, version: str) -> str | None:
    """Prefer release links / assets, then fall back to Generic Package Registry URL."""
    assets = release.get("assets") or {}
    for link in assets.get("links") or []:
        name = str(link.get("name") or "")
        url = str(link.get("url") or "")
        if name == asset_name or url.rstrip("/").endswith(asset_name):
            return url
    for source in assets.get("sources") or []:
        url = str(source.get("url") or "")
        if url.rstrip("/").endswith(asset_name):
            return url
    # Generic Package Registry layout used by .gitlab-ci.yml
    encoded = urllib.parse.quote(GITLAB_PROJECT, safe="")
    tag = release.get("tag_name") or f"v{version}"
    return (
        f"{GITLAB_HOST}/api/v4/projects/{encoded}/packages/generic/"
        f"browser-tool/{tag}/{asset_name}"
    )


def extract_binaries(archive: Path, dest_dir: Path) -> list[Path]:
    """Extract only app binaries (and optional icon.png) into dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    names = set(_binary_names())
    names.add("icon.png")
    written: list[Path] = []

    def _take(member_name: str, extract_fn) -> None:
        base = Path(member_name).name
        if base not in names:
            return
        out = dest_dir / base
        extract_fn(out)
        if base in _binary_names() and sys.platform != "win32":
            out.chmod(out.stat().st_mode | 0o111)
        written.append(out)

    if archive.suffix == ".zip" or zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                base = Path(info.filename).name
                if base not in names:
                    continue

                def _write(out: Path, _info=info) -> None:
                    with zf.open(_info) as src, out.open("wb") as dst:
                        shutil.copyfileobj(src, dst)

                _take(info.filename, _write)
    else:
        with tarfile.open(archive, "r:*") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                base = Path(member.name).name
                if base not in names:
                    continue

                def _write(out: Path, _member=member) -> None:
                    src = tf.extractfile(_member)
                    if src is None:
                        raise RuntimeError(f"Cannot extract {_member.name}")
                    with src, out.open("wb") as dst:
                        shutil.copyfileobj(src, dst)

                _take(member.name, _write)

    required = set(_binary_names())
    got = {p.name for p in written}
    missing = required - got
    if missing:
        raise RuntimeError(f"Archive missing required files: {', '.join(sorted(missing))}")
    return written


def _spawn_helper_and_exit(staging: Path) -> None:
    """Replace binaries after this process exits, then relaunch Config."""
    install = app_dir()
    config_bin = install / _config_binary_name()
    pid = os.getpid()
    helper_dir = Path(tempfile.mkdtemp(prefix="browser-tool-update-"))
    log = get_logger()

    if sys.platform == "win32":
        helper = helper_dir / "apply_update.bat"
        lines = [
            "@echo off",
            f":waitloop",
            f'tasklist /FI "PID eq {pid}" 2>NUL | find "{pid}" >NUL',
            "if not errorlevel 1 (",
            "  timeout /t 1 /nobreak >NUL",
            "  goto waitloop",
            ")",
        ]
        for name in _binary_names():
            src = staging / name
            dest = install / name
            lines.append(f'copy /Y "{src}" "{dest}" >NUL')
        icon = staging / "icon.png"
        if icon.is_file():
            lines.append(f'copy /Y "{icon}" "{install / "icon.png"}" >NUL')
        lines.extend(
            [
                f'start "" "{config_bin}"',
                f'rmdir /s /q "{staging}"',
                f'del "%~f0"',
                f'rmdir "{helper_dir}" 2>NUL',
            ]
        )
        helper.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        log.info("Starting update helper %s", helper)
        creationflags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags |= subprocess.CREATE_NO_WINDOW
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            ["cmd", "/c", str(helper)],
            cwd=str(install),
            creationflags=creationflags,
            close_fds=True,
        )
    else:
        helper = helper_dir / "apply_update.sh"
        script = [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            f"while kill -0 {pid} 2>/dev/null; do sleep 0.5; done",
            "sleep 0.5",
        ]
        for name in _binary_names():
            script.append(f'install -m 755 "{staging / name}" "{install / name}"')
        icon = staging / "icon.png"
        if icon.is_file():
            script.append(f'install -m 644 "{icon}" "{install / "icon.png"}"')
        script.extend(
            [
                f'"{config_bin}" &',
                f'rm -rf "{staging}"',
                f'rm -f "{helper}"',
                f'rmdir "{helper_dir}" 2>/dev/null || true',
            ]
        )
        helper.write_text("\n".join(script) + "\n", encoding="utf-8")
        helper.chmod(0o755)
        log.info("Starting update helper %s", helper)
        subprocess.Popen(
            ["/bin/bash", str(helper)],
            cwd=str(install),
            start_new_session=True,
            close_fds=True,
        )


def download_and_stage(release: ReleaseInfo) -> Path:
    """Download release archive and extract binaries to a temp staging dir."""
    work = Path(tempfile.mkdtemp(prefix="browser-tool-dl-"))
    archive = work / release.asset_name
    staging = work / "staging"
    get_logger().info(
        "Downloading %s from %s", release.asset_name, release.download_url
    )
    _download(release.download_url, archive)
    extract_binaries(archive, staging)
    return staging


def check_for_update() -> tuple[str, ReleaseInfo | None]:
    """
    Returns (status, release).
    status: 'dev' | 'uptodate' | 'available' | 'error'
    """
    if not is_frozen():
        return "dev", None
    try:
        release = fetch_latest_release()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        log_exception("Update check failed", exc)
        raise
    if not is_newer(release.version, __version__):
        return "uptodate", release
    return "available", release


def apply_update(release: ReleaseInfo) -> None:
    """Download, stage, spawn helper, caller must exit the Config process."""
    if not is_frozen():
        raise RuntimeError("Updates only apply to packaged installs")
    staging = download_and_stage(release)
    _spawn_helper_and_exit(staging)


def run_update_in_background(
    on_status,
    on_done,
    *,
    apply: bool = False,
    release: ReleaseInfo | None = None,
) -> None:
    """
    Background helper for the Config UI.
    on_status(msg), on_done(ok, message, release_or_none)
    """

    def worker() -> None:
        try:
            if apply:
                if release is None:
                    raise RuntimeError("No release to apply")
                on_status(f"Downloading {release.version}…")
                apply_update(release)
                on_done(True, "restart", release)
                return
            on_status("Checking for updates…")
            status, info = check_for_update()
            if status == "dev":
                on_done(True, "dev", None)
            elif status == "uptodate":
                on_done(True, "uptodate", info)
            else:
                on_done(True, "available", info)
        except Exception as exc:  # noqa: BLE001
            log_exception("Update failed", exc)
            on_done(False, str(exc), None)

    threading.Thread(target=worker, daemon=True).start()
