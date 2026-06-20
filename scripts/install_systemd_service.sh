#!/usr/bin/env bash
set -euo pipefail

SERVICE_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/systemd/moggie.service"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${SUDO_USER:-$USER}"
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Expected virtualenv python at $PYTHON_BIN. Create it and install dependencies before installing the service." >&2
  exit 1
fi

sed \
  -e "s|WorkingDirectory=/opt/moggie|WorkingDirectory=$REPO_ROOT|" \
  -e "s|ExecStart=/opt/moggie/.venv/bin/python -m app.main|ExecStart=$PYTHON_BIN -m app.main|" \
  -e "s|User=pi|User=$SERVICE_USER|" \
  -e "s|Group=pi|Group=$SERVICE_GROUP|" \
  "$SERVICE_SOURCE" | sudo tee /etc/systemd/system/moggie.service >/dev/null
sudo install -d -m 0755 /etc/moggie
if [[ ! -f /etc/moggie/moggie.env ]]; then
  sudo cp "$REPO_ROOT/config_presets/booth_safe.env" /etc/moggie/moggie.env
fi
sudo systemctl daemon-reload
sudo systemctl enable moggie.service
echo "Installed moggie.service for $SERVICE_USER at $REPO_ROOT and /etc/moggie/moggie.env."
echo "Start with: sudo systemctl start moggie.service"
