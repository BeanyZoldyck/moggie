#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  python3-opencv \
  python3-pygame \
  libsdl2-2.0-0 \
  redis-server
