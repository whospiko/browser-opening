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
"$PYTHON" -m pip install -q -r requirements.txt
rm -rf dist/browser-tool-config dist/browser-tool dist/browser-tool-linux dist/browser-tool-linux.tar.gz build
CRYPTO_HIDDENS=(
  --hidden-import cryptography
  --hidden-import cryptography.fernet
  --hidden-import keyring
  --hidden-import keyring.backends
  --hidden-import keyring.backends.SecretService
  --hidden-import keyring.backends.chainer
  --hidden-import keyring.backends.fail
  --hidden-import keyring.backends.libsecret
  --hidden-import keyring.backends.kwallet
  --hidden-import secure_store
  --hidden-import version
  --hidden-import updater
)
ICON_ARGS=()
if [[ -f assets/icon.png ]]; then
  ICON_ARGS=(--icon assets/icon.png)
fi
"$PYTHON" -m PyInstaller \
  --noconfirm --clean --onefile --windowed \
  --name browser-tool-config \
  "${ICON_ARGS[@]}" \
  --paths src \
  --collect-all screeninfo \
  --hidden-import tkinter \
  --hidden-import _tkinter \
  --hidden-import hyprland \
  "${CRYPTO_HIDDENS[@]}" \
  src/config_app.py
"$PYTHON" -m PyInstaller \
  --noconfirm --clean --onefile --windowed \
  --name browser-tool \
  "${ICON_ARGS[@]}" \
  --paths src \
  --collect-all screeninfo \
  --hidden-import tkinter \
  --hidden-import _tkinter \
  --hidden-import hyprland \
  "${CRYPTO_HIDDENS[@]}" \
  src/launcher_app.py

STAGE=dist/browser-tool-linux
mkdir -p "$STAGE"
cp -f dist/browser-tool-config dist/browser-tool "$STAGE/"
cp -f install.sh "$STAGE/"
chmod +x "$STAGE/browser-tool-config" "$STAGE/browser-tool" "$STAGE/install.sh"
if [[ -f assets/icon.png ]]; then
  cp -f assets/icon.png "$STAGE/icon.png"
fi
tar -C dist -czf dist/browser-tool-linux.tar.gz browser-tool-linux

echo "Built binaries:"
ls -l dist/browser-tool-config dist/browser-tool
echo "Ship this archive:"
ls -l dist/browser-tool-linux.tar.gz
echo
echo "Users: download the .tar.gz, then:"
echo "  tar xf browser-tool-linux.tar.gz"
echo "  cd browser-tool-linux && ./install.sh"
