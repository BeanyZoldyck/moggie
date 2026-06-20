#!/usr/bin/env bash
set -euo pipefail

export MOGGIE_ENV="${MOGGIE_ENV:-production}"
export MOGGIE_PLACEHOLDER_FRAMES="${MOGGIE_PLACEHOLDER_FRAMES:-0}"
PYTHON="${PYTHON:-python3}"

"$PYTHON" -m app.main
