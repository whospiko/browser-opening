#!/usr/bin/env python3
"""Rewrite src/version.py __version__ from CI_COMMIT_TAG or VERSION env."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def main() -> int:
    tag = (os.environ.get("VERSION") or os.environ.get("CI_COMMIT_TAG") or "").strip()
    if not tag:
        print("VERSION or CI_COMMIT_TAG is required", file=sys.stderr)
        return 1
    version = tag[1:] if tag.lower().startswith("v") else tag
    path = Path(__file__).resolve().parent.parent / "src" / "version.py"
    text = path.read_text(encoding="utf-8")
    updated, n = re.subn(
        r"__version__\s*=\s*['\"][^'\"]*['\"]",
        f'__version__ = "{version}"',
        text,
        count=1,
    )
    if n != 1:
        print(f"Could not find __version__ in {path}", file=sys.stderr)
        return 1
    path.write_text(updated, encoding="utf-8")
    print(f"Baked version {version} into {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
