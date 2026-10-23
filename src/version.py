"""App version and where updates are fetched from.

Set GITLAB_PROJECT to your GitLab path (owner/project) before shipping builds.
CI overwrites __version__ from the git tag (v1.2.3 -> 1.2.3) before PyInstaller.
"""

from __future__ import annotations

__version__ = "0.0.0-dev"

# Public GitLab project path used by the in-app updater (no auth).
# Example: "whospiko/browser-opening"
GITLAB_PROJECT = "whospiko/browser-opening"

GITLAB_HOST = "https://gitlab.com"
