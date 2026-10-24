"""App version and where updates are fetched from.

CI overwrites __version__ from the git tag (v1.2.3 -> 1.2.3) before PyInstaller.
Public downloads and in-app updates use Cloudflare R2 (not the private GitLab repo).
"""

from __future__ import annotations

__version__ = "0.0.0-dev"

# Public base URL for R2 custom domain (no trailing slash).
# Objects: {R2_PUBLIC_BASE}/v1.2.3/browser-tool-setup.exe
#          {R2_PUBLIC_BASE}/latest/version.json
R2_PUBLIC_BASE = "https://download-hengkakada.thecapy.org"

# Kept for docs / GitLab package mirror; updater uses R2 only.
GITLAB_PROJECT = "whospiko/browser-opening"
GITLAB_HOST = "https://gitlab.com"
