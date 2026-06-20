#!/usr/bin/env bash
set -euo pipefail

SERVICE_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/systemd/moggie.service"
sudo cp "$SERVICE_SOURCE" /etc/systemd/system/moggie.service
sudo install -d -m 0755 /etc/moggie
if [[ ! -f /etc/moggie/moggie.env ]]; then
  sudo cp "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/config_presets/booth_safe.env" /etc/moggie/moggie.env
fi
sudo systemctl daemon-reload
sudo systemctl enable moggie.service
echo "Installed moggie.service and /etc/moggie/moggie.env. Start with: sudo systemctl start moggie.service"
