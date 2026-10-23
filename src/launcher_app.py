from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from app_log import log_exception, setup_logging
from browser import BrowserNotFoundError, launch_screens
from config import load_config
from paths import config_path, log_path


def _show_error(message: str) -> None:
    detail = f"{message}\n\nSee log: {log_path()}"
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror("POS Launcher", detail)
        root.destroy()
    except Exception:
        sys.stderr.write(f"POS Launcher: {detail}\n")


def main() -> int:
    log = setup_logging("launcher")
    log.info("Launcher starting")
    path = config_path()
    try:
        cfg = load_config(path)
    except FileNotFoundError:
        log.error("No config.json at %s", path)
        _show_error("No config.json found. Run the Config app first.")
        return 1
    except Exception as exc:  # noqa: BLE001
        log_exception("Could not read config.json", exc)
        _show_error(f"Could not read config.json:\n{exc}")
        return 1

    errors = cfg.validate()
    if errors:
        log.error("Config invalid: %s", "; ".join(errors))
        _show_error("Config is invalid:\n" + "\n".join(errors) + "\n\nRun the Config app.")
        return 1

    try:
        launch_screens(cfg)
    except BrowserNotFoundError as exc:
        log_exception("Browser not found", exc)
        _show_error(str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001
        log_exception("Launch failed", exc)
        _show_error(str(exc))
        return 1
    log.info("Launcher finished successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
