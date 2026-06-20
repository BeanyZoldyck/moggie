#!/usr/bin/env bash
set -euo pipefail

SERVICE_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/systemd/moggie.service"
sudo cp "$SERVICE_SOURCE" /etc/systemd/system/moggie.service
sudo systemctl daemon-reload
sudo systemctl enable moggie.service
echo "Installed moggie.service. Start with: sudo systemctl start moggie.service"
