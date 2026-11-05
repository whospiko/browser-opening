from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app_log import get_logger
from paths import config_path, example_config_path
from secure_store import (
    ConfigSecurityError,
    decrypt_envelope,
    encrypt_payload,
    is_encrypted_envelope,
)

ALLOWED_BROWSERS = ("edge", "chrome", "brave")
ALLOWED_WINDOW_MODES = ("fullscreen", "maximized", "kiosk")
ALLOWED_OPEN_AS = ("window", "tab")
DEFAULT_OPEN_DELAY_SECONDS = 0.4
MAX_OPEN_DELAY_SECONDS = 120.0


@dataclass
class ScreenConfig:
    name: str = ""
    url: str = ""
    monitor: int = 0
    window_mode: str = "fullscreen"
    open_as: str = "window"
    enabled: bool = True


def _default_screens() -> list[ScreenConfig]:
    return [
        ScreenConfig(name="cashier", url="https://example.com/cashier", monitor=0),
        ScreenConfig(
            name="customer", url="https://example.com/customer-display", monitor=1
        ),
    ]


@dataclass
class AppConfig:
    browser: str = "edge"
    open_on_startup: bool = False
    open_delay_seconds: float = DEFAULT_OPEN_DELAY_SECONDS
    screens: list[ScreenConfig] = field(default_factory=_default_screens)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.browser not in ALLOWED_BROWSERS:
            errors.append("Browser must be Edge, Chrome, or Brave.")
        if self.open_delay_seconds < 0:
            errors.append("Open delay must be 0 or greater.")
        elif self.open_delay_seconds > MAX_OPEN_DELAY_SECONDS:
            errors.append(f"Open delay must be at most {int(MAX_OPEN_DELAY_SECONDS)} seconds.")
        if not self.screens:
            errors.append("Add at least one screen.")
            return errors
        if not any(screen.enabled for screen in self.screens):
            errors.append("Turn on at least one screen.")

        seen_names: set[str] = set()
        monitors_with_window: set[int] = set()
        for index, screen in enumerate(self.screens, start=1):
            label = screen.name.strip() or f"Screen {index}"
            if not screen.name.strip():
                errors.append(f"Screen {index}: name is required.")
            else:
                key = screen.name.strip().lower()
                if key in seen_names:
                    errors.append(f"Screen name '{screen.name.strip()}' is used more than once.")
                seen_names.add(key)
            if not screen.url.strip():
                errors.append(f"{label}: URL is required.")
            if screen.monitor < 0:
                errors.append(f"{label}: monitor must be 0 or greater.")
            if screen.window_mode not in ALLOWED_WINDOW_MODES:
                errors.append(f"{label}: window mode must be Fullscreen, Maximized, or Kiosk.")
            if not screen.enabled:
                continue
            open_as = screen.open_as if screen.open_as in ALLOWED_OPEN_AS else "window"
            if open_as == "tab":
                if screen.monitor not in monitors_with_window:
                    errors.append(
                        f"{label}: Open as Tab needs a Window on the same monitor "
                        "above it in the list (and turned on)."
                    )
            else:
                monitors_with_window.add(screen.monitor)
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "browser": self.browser,
            "open_on_startup": self.open_on_startup,
            "open_delay_seconds": float(self.open_delay_seconds),
            "screens": [
                {
                    "name": screen.name.strip(),
                    "url": screen.url.strip(),
                    "monitor": int(screen.monitor),
                    "window_mode": screen.window_mode,
                    "open_as": screen.open_as if screen.open_as in ALLOWED_OPEN_AS else "window",
                    "enabled": bool(screen.enabled),
                }
                for screen in self.screens
            ],
        }


def _normalize_window_mode(raw: Any, fallback: str = "fullscreen") -> str:
    if isinstance(raw, bool):
        return "fullscreen" if raw else "maximized"
    mode = str(raw or fallback).strip().lower()
    if mode in ALLOWED_WINDOW_MODES:
        return mode
    return fallback if fallback in ALLOWED_WINDOW_MODES else "fullscreen"


def _normalize_open_as(raw: Any, fallback: str = "window") -> str:
    mode = str(raw or fallback).strip().lower()
    if mode in ALLOWED_OPEN_AS:
        return mode
    return fallback if fallback in ALLOWED_OPEN_AS else "window"


def _legacy_global_window_mode(data: dict[str, Any]) -> str:
    raw = data.get("window_mode")
    if raw is None:
        raw = data.get("fullscreen")
    if raw is None:
        return "fullscreen"
    return _normalize_window_mode(raw, "fullscreen")


def _screen_from_data(
    data: Any,
    fallback: ScreenConfig | None = None,
    *,
    default_window_mode: str = "fullscreen",
) -> ScreenConfig:
    fb = fallback or ScreenConfig()
    if not isinstance(data, dict):
        return ScreenConfig(
            name=fb.name,
            url=fb.url,
            monitor=fb.monitor,
            window_mode=fb.window_mode or default_window_mode,
            open_as=fb.open_as or "window",
            enabled=fb.enabled,
        )
    name = data.get("name", fb.name)
    url = data.get("url", fb.url)
    monitor = data.get("monitor", fb.monitor)
    try:
        monitor_i = int(monitor)
    except (TypeError, ValueError):
        monitor_i = fb.monitor
    if "window_mode" in data:
        window_raw = data.get("window_mode")
    else:
        window_raw = default_window_mode
    open_as_raw = data.get("open_as", fb.open_as or "window")
    if "enabled" in data:
        enabled = bool(data.get("enabled"))
    else:
        enabled = fb.enabled
    return ScreenConfig(
        name=str(name or ""),
        url=str(url or ""),
        monitor=monitor_i,
        window_mode=_normalize_window_mode(window_raw, default_window_mode),
        open_as=_normalize_open_as(open_as_raw, "window"),
        enabled=enabled,
    )


def _screens_from_data(data: dict[str, Any], defaults: list[ScreenConfig]) -> list[ScreenConfig]:
    legacy_mode = _legacy_global_window_mode(data)
    raw = data.get("screens")
    if isinstance(raw, list):
        screens = [
            _screen_from_data(item, default_window_mode=legacy_mode) for item in raw
        ]
        return screens if screens else list(defaults)

    # Migrate legacy cashier / customer objects.
    screens: list[ScreenConfig] = []
    if "cashier" in data:
        cashier_default = next(
            (s for s in defaults if s.name == "cashier"), ScreenConfig(name="cashier")
        )
        screen = _screen_from_data(
            data.get("cashier"), cashier_default, default_window_mode=legacy_mode
        )
        if not screen.name.strip():
            screen.name = "cashier"
        screens.append(screen)
    if "customer" in data:
        customer_default = next(
            (s for s in defaults if s.name == "customer"), ScreenConfig(name="customer")
        )
        screen = _screen_from_data(
            data.get("customer"), customer_default, default_window_mode=legacy_mode
        )
        if not screen.name.strip():
            screen.name = "customer"
        screens.append(screen)
    return screens if screens else list(defaults)


def _normalize_open_delay(raw: Any, fallback: float = DEFAULT_OPEN_DELAY_SECONDS) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return fallback
    if value < 0:
        return fallback
    if value > MAX_OPEN_DELAY_SECONDS:
        return MAX_OPEN_DELAY_SECONDS
    return value


def config_from_dict(data: dict[str, Any]) -> AppConfig:
    defaults = AppConfig()
    browser = str(data.get("browser", defaults.browser)).strip().lower()
    delay_raw = data.get("open_delay_seconds", defaults.open_delay_seconds)
    return AppConfig(
        browser=browser,
        open_on_startup=bool(data.get("open_on_startup", defaults.open_on_startup)),
        open_delay_seconds=_normalize_open_delay(delay_raw, defaults.open_delay_seconds),
        screens=_screens_from_data(data, defaults.screens),
    )


def load_json_file(path: Path, *, decrypt: bool = True) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    if decrypt and is_encrypted_envelope(data):
        get_logger().info("Config file %s: encrypted envelope", path)
        return decrypt_envelope(data)
    get_logger().info("Config file %s: plaintext", path)
    return data


def default_config() -> AppConfig:
    example = example_config_path()
    if example.exists():
        # Example stays plaintext documentation; never treat as encrypted.
        return config_from_dict(load_json_file(example, decrypt=False))
    return AppConfig()


def load_config(path: Path | None = None) -> AppConfig:
    target = path or config_path()
    if not target.exists():
        get_logger().error("Config not found: %s", target)
        raise FileNotFoundError(str(target))
    cfg = config_from_dict(load_json_file(target))
    get_logger().info(
        "Config loaded: browser=%s screens=%d open_on_startup=%s open_delay_seconds=%s",
        cfg.browser,
        len(cfg.screens),
        cfg.open_on_startup,
        cfg.open_delay_seconds,
    )
    return cfg


def load_config_or_default(path: Path | None = None) -> AppConfig:
    target = path or config_path()
    if not target.exists():
        get_logger().info("Config missing (%s); using defaults", target)
        return default_config()
    return load_config(target)


def save_config(cfg: AppConfig, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    envelope = encrypt_payload(cfg.to_dict())
    with target.open("w", encoding="utf-8") as handle:
        json.dump(envelope, handle, indent=2)
        handle.write("\n")
    get_logger().info(
        "Config saved (encrypted): %s browser=%s screens=%d open_on_startup=%s open_delay_seconds=%s",
        target,
        cfg.browser,
        len(cfg.screens),
        cfg.open_on_startup,
        cfg.open_delay_seconds,
    )
    return target
