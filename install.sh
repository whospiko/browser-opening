#!/usr/bin/env bash
# Install Browser Tool into ~/browser-tool (or a custom path).
# Run from the extracted package directory that contains the binaries.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_DEST="${HOME}/browser-tool"
DEST="${1:-$DEFAULT_DEST}"

need() {
  local name="$1"
  if [[ ! -f "$SCRIPT_DIR/$name" ]]; then
    echo "Missing $name next to install.sh (expected in $SCRIPT_DIR)" >&2
    exit 1
  fi
}

need browser-tool-config
need browser-tool

mkdir -p "$DEST/log"
install -m 755 "$SCRIPT_DIR/browser-tool-config" "$DEST/browser-tool-config"
install -m 755 "$SCRIPT_DIR/browser-tool" "$DEST/browser-tool"

if [[ -f "$SCRIPT_DIR/icon.png" ]]; then
  install -m 644 "$SCRIPT_DIR/icon.png" "$DEST/icon.png"
fi

# Optional desktop entry for Config (user Applications menu)
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_LINE=""
if [[ -f "$DEST/icon.png" ]]; then
  ICON_LINE="Icon=$DEST/icon.png"
fi
DESKTOP_BODY=$(cat <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Browser Tool Config
Comment=Configure dual-screen POS browsers
Exec=$DEST/browser-tool-config
Path=$DEST
Terminal=false
Categories=Utility;
${ICON_LINE}
EOF
)
if mkdir -p "$APPS" 2>/dev/null && printf '%s\n' "$DESKTOP_BODY" > "$APPS/browser-tool-config.desktop" 2>/dev/null; then
  chmod 644 "$APPS/browser-tool-config.desktop" 2>/dev/null || true
fi

echo "Installed to: $DEST"
echo "  Config:   $DEST/browser-tool-config"
echo "  Launcher: $DEST/browser-tool"
echo "  Logs:     $DEST/log/"
echo
echo "Run Config first to create config.json, then open screens with the launcher."
