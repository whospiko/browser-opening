#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON=python3.12
else
  PYTHON=python3
fi
exec "$PYTHON" src/config_app.py "$@"
