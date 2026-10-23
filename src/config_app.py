from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from app_log import get_logger, log_exception, setup_logging
from browser import BrowserNotFoundError, launch_screens
from config import (
    ALLOWED_BROWSERS,
    ALLOWED_WINDOW_MODES,
    DEFAULT_OPEN_DELAY_SECONDS,
    MAX_OPEN_DELAY_SECONDS,
    AppConfig,
    ScreenConfig,
    load_config_or_default,
    save_config,
)
from monitors import list_monitors
from paths import config_path, is_frozen, log_path
from secure_store import ConfigSecurityError
from startup import apply as apply_startup
from updater import ReleaseInfo, run_update_in_background
from version import __version__


class ScreenRow:
    def __init__(
        self,
        parent: ttk.Frame,
        monitor_labels: list[str],
        on_remove,
        on_move_up,
        on_move_down,
        name: str = "",
        url: str = "",
        monitor: int = 0,
        window_mode: str = "fullscreen",
    ) -> None:
        self.frame = ttk.Frame(parent)
        self.name_var = tk.StringVar(value=name)
        self.url_var = tk.StringVar(value=url)
        self.window_mode_var = tk.StringVar(
            value=window_mode if window_mode in ALLOWED_WINDOW_MODES else "fullscreen"
        )
        self.order_var = tk.StringVar(value="1")
        self.monitor_combo = ttk.Combobox(self.frame, state="readonly")
        self.monitor_combo.configure(values=monitor_labels or ["Monitor 0 (none detected)"])
        self.window_combo = ttk.Combobox(
            self.frame,
            textvariable=self.window_mode_var,
            values=ALLOWED_WINDOW_MODES,
            state="readonly",
            width=12,
        )

        ttk.Label(self.frame, textvariable=self.order_var, width=3, anchor="center").grid(
            row=0, column=0, sticky="w", padx=(0, 4)
        )
        move = ttk.Frame(self.frame)
        move.grid(row=0, column=1, sticky="w", padx=(0, 6))
        self.up_btn = ttk.Button(move, text="↑", width=3, command=lambda: on_move_up(self))
        self.up_btn.pack(side="left", padx=(0, 2))
        self.down_btn = ttk.Button(move, text="↓", width=3, command=lambda: on_move_down(self))
        self.down_btn.pack(side="left")
        ttk.Entry(self.frame, textvariable=self.name_var, width=14).grid(
            row=0, column=2, sticky="ew", padx=(0, 6)
        )
        ttk.Entry(self.frame, textvariable=self.url_var).grid(
            row=0, column=3, sticky="ew", padx=(0, 6)
        )
        self.monitor_combo.grid(row=0, column=4, sticky="ew", padx=(0, 6))
        self.window_combo.grid(row=0, column=5, sticky="ew", padx=(0, 6))
        ttk.Button(self.frame, text="Remove", width=8, command=lambda: on_remove(self)).grid(
            row=0, column=6, sticky="e"
        )
        self.frame.columnconfigure(3, weight=1)
        self.frame.columnconfigure(4, weight=1)
        self._select_monitor(monitor)

    def set_order(self, index: int, total: int) -> None:
        self.order_var.set(str(index + 1))
        self.up_btn.configure(state="disabled" if index <= 0 else "normal")
        self.down_btn.configure(state="disabled" if index >= total - 1 else "normal")

    def _select_monitor(self, index: int) -> None:
        values = list(self.monitor_combo.cget("values") or ())
        if not values:
            return
        if 0 <= index < len(values):
            self.monitor_combo.current(index)
        else:
            self.monitor_combo.current(0)

    def set_monitor_labels(self, labels: list[str], keep_index: int | None = None) -> None:
        current = self.monitor_combo.current()
        index = keep_index if keep_index is not None else max(current, 0)
        self.monitor_combo.configure(values=labels or ["Monitor 0 (none detected)"])
        self._select_monitor(index)

    def to_config(self) -> ScreenConfig:
        mode = self.window_mode_var.get()
        if mode not in ALLOWED_WINDOW_MODES:
            mode = "fullscreen"
        return ScreenConfig(
            name=self.name_var.get().strip(),
            url=self.url_var.get().strip(),
            monitor=max(self.monitor_combo.current(), 0),
            window_mode=mode,
        )


class ConfigApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Browser Tool Config")
        self.resizable(True, True)
        self.minsize(860, 520)

        self.browser_var = tk.StringVar(value="edge")
        self.startup_mode = tk.StringVar(value="manual")
        self.open_delay_var = tk.StringVar(value=str(DEFAULT_OPEN_DELAY_SECONDS))
        self._save_warned = False
        self._monitors = []
        self._screen_rows: list[ScreenRow] = []
        self._monitor_labels: list[str] = []

        self._build()
        self._load_into_form()
        self.after(50, self._center_on_screen)

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}
        root = ttk.Frame(self, padding=16)
        root.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        top = ttk.Frame(root)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Browser").grid(row=0, column=0, sticky="w", **pad)
        browser = ttk.Combobox(
            top,
            textvariable=self.browser_var,
            values=ALLOWED_BROWSERS,
            state="readonly",
            width=16,
        )
        browser.grid(row=0, column=1, sticky="w", **pad)

        ttk.Separator(root).grid(row=1, column=0, sticky="ew", pady=8)

        screens_header = ttk.Frame(root)
        screens_header.grid(row=2, column=0, sticky="nsew")
        screens_header.columnconfigure(0, weight=1)
        screens_header.rowconfigure(1, weight=1)

        header_row = ttk.Frame(screens_header)
        header_row.grid(row=0, column=0, sticky="ew", padx=12, pady=(0, 4))
        header_row.columnconfigure(0, weight=1)
        ttk.Label(header_row, text="Screens").pack(side="left")
        ttk.Button(header_row, text="Add screen", command=self._add_screen).pack(side="right")

        canvas_wrap = ttk.Frame(screens_header)
        canvas_wrap.grid(row=1, column=0, sticky="nsew", padx=12)
        canvas_wrap.columnconfigure(0, weight=1)
        canvas_wrap.rowconfigure(0, weight=1)

        self._screens_canvas = tk.Canvas(canvas_wrap, highlightthickness=0, height=180)
        self._screens_scroll = ttk.Scrollbar(
            canvas_wrap, orient="vertical", command=self._screens_canvas.yview
        )
        self._screens_canvas.configure(yscrollcommand=self._screens_scroll.set)
        self._screens_canvas.grid(row=0, column=0, sticky="nsew")
        self._screens_scroll.grid(row=0, column=1, sticky="ns")

        self._screens_inner = ttk.Frame(self._screens_canvas)
        self._screens_window = self._screens_canvas.create_window(
            (0, 0), window=self._screens_inner, anchor="nw"
        )
        self._screens_inner.columnconfigure(0, weight=1)
        self._screens_inner.bind("<Configure>", self._on_screens_configure)
        self._screens_canvas.bind("<Configure>", self._on_canvas_configure)

        labels = ttk.Frame(self._screens_inner)
        labels.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        labels.columnconfigure(3, weight=1)
        labels.columnconfigure(4, weight=1)
        ttk.Label(labels, text="#", width=3, anchor="center").grid(
            row=0, column=0, sticky="w", padx=(0, 4)
        )
        ttk.Label(labels, text="Order", width=8).grid(row=0, column=1, sticky="w", padx=(0, 6))
        ttk.Label(labels, text="Name").grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Label(labels, text="URL").grid(row=0, column=3, sticky="w", padx=(0, 6))
        ttk.Label(labels, text="Monitor").grid(row=0, column=4, sticky="w", padx=(0, 6))
        ttk.Label(labels, text="Window").grid(row=0, column=5, sticky="w", padx=(0, 6))
        ttk.Label(labels, text="").grid(row=0, column=6, sticky="e")

        self._rows_frame = ttk.Frame(self._screens_inner)
        self._rows_frame.grid(row=1, column=0, sticky="ew")
        self._rows_frame.columnconfigure(0, weight=1)

        ttk.Separator(root).grid(row=3, column=0, sticky="ew", pady=8)

        options = ttk.Frame(root)
        options.grid(row=4, column=0, sticky="ew")
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="How to open").grid(row=0, column=0, sticky="nw", **pad)
        mode = ttk.Frame(options)
        mode.grid(row=0, column=1, sticky="w", **pad)
        ttk.Radiobutton(
            mode, text="Manual", value="manual", variable=self.startup_mode
        ).pack(anchor="w")
        ttk.Radiobutton(
            mode,
            text="When computer starts",
            value="startup",
            variable=self.startup_mode,
        ).pack(anchor="w")

        ttk.Label(options, text="Delay between screens").grid(
            row=1, column=0, sticky="w", **pad
        )
        delay_row = ttk.Frame(options)
        delay_row.grid(row=1, column=1, sticky="w", **pad)
        ttk.Spinbox(
            delay_row,
            from_=0,
            to=int(MAX_OPEN_DELAY_SECONDS),
            increment=0.5,
            textvariable=self.open_delay_var,
            width=8,
        ).pack(side="left")
        ttk.Label(delay_row, text="seconds (opens next screen after this wait)").pack(
            side="left", padx=(6, 0)
        )

        self.status = ttk.Label(root, text=f"Config file: {config_path()}")
        self.status.grid(row=5, column=0, sticky="w", padx=12, pady=(12, 4))

        version_row = ttk.Frame(root)
        version_row.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 4))
        version_row.columnconfigure(0, weight=1)
        self.version_label = ttk.Label(
            version_row, text=f"Version {__version__}", foreground="#666666"
        )
        self.version_label.grid(row=0, column=0, sticky="w")
        self.update_status = ttk.Label(version_row, text="", foreground="#666666")
        self.update_status.grid(row=0, column=1, sticky="e")

        buttons = ttk.Frame(root)
        buttons.grid(row=7, column=0, sticky="e", pady=(12, 0))
        self._update_btn = ttk.Button(buttons, text="Update", command=self._on_update)
        self._update_btn.pack(side="left", padx=4)
        ttk.Button(buttons, text="Save", command=self._on_save).pack(side="left", padx=4)
        ttk.Button(buttons, text="Save & Test Open", command=self._on_save_and_test).pack(
            side="left", padx=4
        )
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="left", padx=4)

        self._pending_release: ReleaseInfo | None = None
        self._fill_monitors()

    def _on_screens_configure(self, _event=None) -> None:
        self._screens_canvas.configure(scrollregion=self._screens_canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._screens_canvas.itemconfigure(self._screens_window, width=event.width)

    def _fill_monitors(self) -> None:
        try:
            self._monitors = list_monitors()
        except Exception as exc:  # noqa: BLE001 — show any detection failure in the UI
            self._monitors = []
            self.status.configure(text=f"Could not list monitors: {exc}")
        self._monitor_labels = [m.label for m in self._monitors] or [
            "Monitor 0 (none detected)"
        ]
        for row in self._screen_rows:
            row.set_monitor_labels(self._monitor_labels)

    def _clear_rows(self) -> None:
        for row in list(self._screen_rows):
            row.frame.destroy()
        self._screen_rows.clear()

    def _add_screen(
        self,
        name: str = "",
        url: str = "",
        monitor: int = 0,
        window_mode: str = "fullscreen",
        *,
        relayout: bool = True,
    ) -> None:
        row = ScreenRow(
            self._rows_frame,
            self._monitor_labels,
            on_remove=self._remove_screen,
            on_move_up=self._move_screen_up,
            on_move_down=self._move_screen_down,
            name=name,
            url=url,
            monitor=monitor,
            window_mode=window_mode,
        )
        self._screen_rows.append(row)
        if relayout:
            self._layout_rows()

    def _remove_screen(self, row: ScreenRow) -> None:
        if len(self._screen_rows) <= 1:
            messagebox.showinfo(
                "Screens",
                "Keep at least one screen. Add another before removing this one.",
                parent=self,
            )
            return
        row.frame.destroy()
        self._screen_rows.remove(row)
        self._layout_rows()

    def _move_screen_up(self, row: ScreenRow) -> None:
        index = self._screen_rows.index(row)
        if index <= 0:
            return
        self._screen_rows[index - 1], self._screen_rows[index] = (
            self._screen_rows[index],
            self._screen_rows[index - 1],
        )
        self._layout_rows()

    def _move_screen_down(self, row: ScreenRow) -> None:
        index = self._screen_rows.index(row)
        if index >= len(self._screen_rows) - 1:
            return
        self._screen_rows[index + 1], self._screen_rows[index] = (
            self._screen_rows[index],
            self._screen_rows[index + 1],
        )
        self._layout_rows()

    def _layout_rows(self) -> None:
        total = len(self._screen_rows)
        for index, row in enumerate(self._screen_rows):
            row.frame.grid(row=index, column=0, sticky="ew", pady=3)
            row.frame.columnconfigure(3, weight=1)
            row.frame.columnconfigure(4, weight=1)
            row.set_order(index, total)
        self._on_screens_configure()

    def _center_on_screen(self) -> None:
        self.update_idletasks()
        width = max(self.winfo_width(), self.winfo_reqwidth(), 860)
        height = max(self.winfo_height(), self.winfo_reqheight(), 520)
        target = next((m for m in self._monitors if m.is_primary), None)
        if target is None and self._monitors:
            target = self._monitors[0]
        if target is not None:
            x = target.x + max((target.width - width) // 2, 0)
            y = target.y + max((target.height - height) // 2, 0)
        else:
            x = max((self.winfo_screenwidth() - width) // 2, 0)
            y = max((self.winfo_screenheight() - height) // 2, 0)
        self.geometry(f"{width}x{height}+{x}+{y}")
        try:
            import hyprland

            if hyprland.available():
                client = hyprland.wait_for_window(os.getpid(), timeout=2.0)
                pid = int(client.get("pid") or os.getpid()) if client else os.getpid()
                hyprland.float_and_center(pid, target.name if target else None)
        except Exception:
            pass

    def _load_into_form(self) -> None:
        try:
            cfg = load_config_or_default()
        except ConfigSecurityError as exc:
            log_exception("Cannot load config", exc)
            messagebox.showerror(
                "Cannot load config",
                f"{exc}\n\nSee log: {log_path()}",
                parent=self,
            )
            cfg = AppConfig(screens=[])
        self.browser_var.set(cfg.browser if cfg.browser in ALLOWED_BROWSERS else "edge")
        self.startup_mode.set("startup" if cfg.open_on_startup else "manual")
        self.open_delay_var.set(str(cfg.open_delay_seconds))
        self._clear_rows()
        screens = cfg.screens or [
            ScreenConfig(name="cashier", url="", monitor=0, window_mode="fullscreen"),
        ]
        for screen in screens:
            self._add_screen(
                name=screen.name,
                url=screen.url,
                monitor=screen.monitor,
                window_mode=screen.window_mode,
                relayout=False,
            )
        self._layout_rows()

    def _parse_open_delay(self) -> float:
        raw = self.open_delay_var.get().strip()
        try:
            return float(raw)
        except ValueError:
            return DEFAULT_OPEN_DELAY_SECONDS

    def _form_config(self) -> AppConfig:
        return AppConfig(
            browser=self.browser_var.get(),
            open_on_startup=self.startup_mode.get() == "startup",
            open_delay_seconds=self._parse_open_delay(),
            screens=[row.to_config() for row in self._screen_rows],
        )

    def _save(self) -> AppConfig | None:
        cfg = self._form_config()
        errors = cfg.validate()
        if errors:
            get_logger().error("Cannot save: %s", "; ".join(errors))
            messagebox.showerror("Cannot save", "\n".join(errors), parent=self)
            return None
        try:
            path = save_config(cfg)
        except (OSError, ConfigSecurityError) as exc:
            log_exception("Cannot save config", exc)
            messagebox.showerror(
                "Cannot save",
                f"{exc}\n\nSee log: {log_path()}",
                parent=self,
            )
            return None
        try:
            apply_startup(cfg.open_on_startup)
        except Exception as exc:  # noqa: BLE001 — OS-specific autostart failures
            messagebox.showwarning(
                "Saved with a warning",
                f"Config was saved to:\n{path}\n\nStartup setting failed:\n{exc}\n\n"
                f"See log: {log_path()}",
                parent=self,
            )
            self.status.configure(text=f"Saved {path} (startup warning)")
            self._save_warned = True
            return cfg
        self._save_warned = False
        self.status.configure(text=f"Saved {path}")
        return cfg

    def _on_save(self) -> None:
        cfg = self._save()
        if cfg is not None and not self._save_warned:
            messagebox.showinfo("Saved", f"Settings saved to:\n{config_path()}", parent=self)

    def _on_save_and_test(self) -> None:
        cfg = self._save()
        if cfg is None:
            return
        try:
            launch_screens(cfg)
        except BrowserNotFoundError as exc:
            log_exception("Browser not found during test open", exc)
            messagebox.showerror(
                "Browser not found",
                f"{exc}\n\nSee log: {log_path()}",
                parent=self,
            )
        except Exception as exc:  # noqa: BLE001
            log_exception("Could not open browsers during test", exc)
            messagebox.showerror(
                "Could not open browsers",
                f"{exc}\n\nSee log: {log_path()}",
                parent=self,
            )

    def _set_update_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self._update_btn.configure(state=state)

    def _on_update(self) -> None:
        if not is_frozen():
            messagebox.showinfo(
                "Update",
                "Updates apply only to installed packaged builds.\n"
                "This is a development run.",
                parent=self,
            )
            return
        self._set_update_busy(True)
        self.update_status.configure(text="Checking…")

        def on_status(msg: str) -> None:
            self.after(0, lambda: self.update_status.configure(text=msg))

        def on_done(ok: bool, message: str, release: ReleaseInfo | None) -> None:
            self.after(0, lambda: self._update_check_finished(ok, message, release))

        run_update_in_background(on_status, on_done, apply=False)

    def _update_check_finished(
        self, ok: bool, message: str, release: ReleaseInfo | None
    ) -> None:
        self._set_update_busy(False)
        if not ok:
            self.update_status.configure(text="")
            messagebox.showerror(
                "Update",
                f"{message}\n\nSee log: {log_path()}",
                parent=self,
            )
            return
        if message == "dev":
            self.update_status.configure(text="")
            messagebox.showinfo(
                "Update",
                "Updates apply only to installed packaged builds.",
                parent=self,
            )
            return
        if message == "uptodate":
            remote = release.version if release else __version__
            self.update_status.configure(text="Up to date")
            messagebox.showinfo(
                "Update",
                f"You are up to date.\nCurrent version: {__version__}\n"
                f"Latest: {remote}",
                parent=self,
            )
            return
        if message == "available" and release is not None:
            self._pending_release = release
            self.update_status.configure(text=f"Update {release.version} available")
            go = messagebox.askyesno(
                "Update",
                f"A newer version is available.\n\n"
                f"Current: {__version__}\n"
                f"Latest: {release.version}\n\n"
                "Download and install now?\n"
                "Config and logs will be kept. The Config app will restart.",
                parent=self,
            )
            if go:
                self._start_apply_update(release)
            return
        self.update_status.configure(text="")

    def _start_apply_update(self, release: ReleaseInfo) -> None:
        self._set_update_busy(True)
        self.update_status.configure(text=f"Downloading {release.version}…")

        def on_status(msg: str) -> None:
            self.after(0, lambda: self.update_status.configure(text=msg))

        def on_done(ok: bool, message: str, _release: ReleaseInfo | None) -> None:
            self.after(0, lambda: self._apply_finished(ok, message))

        run_update_in_background(
            on_status, on_done, apply=True, release=release
        )

    def _apply_finished(self, ok: bool, message: str) -> None:
        if not ok:
            self._set_update_busy(False)
            self.update_status.configure(text="")
            messagebox.showerror(
                "Update",
                f"Update failed:\n{message}\n\nSee log: {log_path()}",
                parent=self,
            )
            return
        # Helper is waiting for this process to exit, then replaces binaries.
        self.update_status.configure(text="Installing… restarting")
        self.destroy()


def main() -> int:
    log = setup_logging("config")
    log.info("Config app starting")
    app = ConfigApp()
    app.mainloop()
    log.info("Config app closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
