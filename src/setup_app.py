from __future__ import annotations

import shutil
import string
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


APP_FOLDER = "browser-tool"
PAYLOAD_NAMES = ("browser-tool-config.exe", "browser-tool.exe")


def _resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # Dev: look next to project dist/
    return Path(__file__).resolve().parent.parent / "dist"


def _payload_path(name: str) -> Path:
    root = _resource_root()
    candidates = [
        root / "payload" / name,
        root / name,
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"Missing packaged binary {name}. Looked in: "
        + ", ".join(str(c) for c in candidates)
    )


def list_drives() -> list[str]:
    drives: list[str] = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        try:
            if root.exists():
                drives.append(f"{letter}:")
        except OSError:
            continue
    return drives


def install_to(drive: str) -> Path:
    letter = drive.rstrip(":\\/")
    target = Path(f"{letter}:\\") / APP_FOLDER
    target.mkdir(parents=True, exist_ok=True)
    (target / "log").mkdir(parents=True, exist_ok=True)
    for name in PAYLOAD_NAMES:
        src = _payload_path(name)
        dest = target / name
        shutil.copy2(src, dest)
    return target


class SetupApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Browser Tool Setup")
        self.resizable(False, False)
        self.minsize(420, 220)

        drives = list_drives()
        if not drives:
            messagebox.showerror("Setup", "No drives were found.")
            self.destroy()
            return

        self.drive_var = tk.StringVar(value=drives[0])
        self.status_var = tk.StringVar(value="Choose a drive, then click Install.")

        frame = ttk.Frame(self, padding=20)
        frame.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        ttk.Label(frame, text="Browser Tool Setup", font=("", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Label(
            frame,
            text="Install folder will be created as  <drive>:\\browser-tool",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Label(frame, text="Drive:").grid(row=2, column=0, sticky="w")
        drive_box = ttk.Combobox(
            frame,
            textvariable=self.drive_var,
            values=drives,
            state="readonly",
            width=8,
        )
        drive_box.grid(row=2, column=1, sticky="w", padx=(8, 0))

        self.preview_var = tk.StringVar()
        self._update_preview()
        self.drive_var.trace_add("write", lambda *_: self._update_preview())
        ttk.Label(frame, textvariable=self.preview_var).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 16)
        )

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(btn_row, text="Install", command=self._on_install).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(btn_row, text="Quit", command=self.destroy).pack(side="right")

        ttk.Label(frame, textvariable=self.status_var).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(16, 0)
        )

    def _update_preview(self) -> None:
        drive = self.drive_var.get().rstrip(":\\/")
        self.preview_var.set(f"Install path: {drive}:\\{APP_FOLDER}")

    def _on_install(self) -> None:
        drive = self.drive_var.get()
        if not drive:
            messagebox.showwarning("Setup", "Select a drive first.")
            return
        try:
            self.status_var.set("Installing…")
            self.update_idletasks()
            target = install_to(drive)
        except Exception as exc:
            self.status_var.set("Install failed.")
            messagebox.showerror("Setup", f"Install failed:\n{exc}")
            return

        self.status_var.set(f"Installed to {target}")
        open_folder = messagebox.askyesno(
            "Setup",
            f"Installed successfully to:\n{target}\n\nOpen the folder now?",
        )
        if open_folder:
            try:
                subprocess.Popen(["explorer", str(target)])
            except OSError:
                pass


def main() -> None:
    if sys.platform != "win32":
        print("browser-tool-setup is for Windows only.", file=sys.stderr)
        raise SystemExit(1)
    app = SetupApp()
    if app.winfo_exists():
        app.mainloop()


if __name__ == "__main__":
    main()
