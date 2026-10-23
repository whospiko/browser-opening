from __future__ import annotations

from dataclasses import dataclass

from screeninfo import get_monitors


@dataclass(frozen=True)
class Monitor:
    index: int
    x: int
    y: int
    width: int
    height: int
    name: str
    is_primary: bool

    @property
    def label(self) -> str:
        primary = " — primary" if self.is_primary else ""
        name = f" {self.name}" if self.name else ""
        return (
            f"Monitor {self.index}{name}: {self.width}×{self.height} "
            f"at ({self.x}, {self.y}){primary}"
        )


def _from_hyprland() -> list[Monitor] | None:
    try:
        import hyprland
    except ImportError:
        return None
    if not hyprland.available():
        return None
    found = hyprland.list_monitor_dicts()
    return [
        Monitor(
            index=index,
            x=int(item["x"]),
            y=int(item["y"]),
            width=int(item["width"]),
            height=int(item["height"]),
            name=str(item.get("name") or ""),
            is_primary=bool(item.get("is_primary")),
        )
        for index, item in enumerate(found)
    ]


def list_monitors() -> list[Monitor]:
    hypr = _from_hyprland()
    if hypr:
        return hypr
    found = get_monitors()
    monitors: list[Monitor] = []
    for index, item in enumerate(found):
        monitors.append(
            Monitor(
                index=index,
                x=int(item.x),
                y=int(item.y),
                width=int(item.width),
                height=int(item.height),
                name=str(getattr(item, "name", "") or ""),
                is_primary=bool(getattr(item, "is_primary", False)),
            )
        )
    return monitors


def require_monitor(monitors: list[Monitor], index: int, role: str) -> Monitor:
    if not monitors:
        raise RuntimeError("No monitors detected.")
    if index < 0 or index >= len(monitors):
        raise RuntimeError(
            f"{role.capitalize()} monitor {index} is not available "
            f"({len(monitors)} monitor(s) detected)."
        )
    return monitors[index]
