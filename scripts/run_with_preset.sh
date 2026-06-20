#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <preset-name|preset-path> [-- app args]" >&2
  echo "Examples: $0 cloud_disabled -- --frames 3" >&2
  echo "          $0 config_presets/booth_safe.env" >&2
  exit 2
fi

PRESET="$1"
shift
if [[ "${1:-}" == "--" ]]; then
  shift
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$PRESET" != */* ]]; then
  PRESET="$ROOT/config_presets/${PRESET}.env"
fi

if [[ ! -f "$PRESET" ]]; then
  echo "Preset not found: $PRESET" >&2
  exit 2
fi

set -a
source "$PRESET"
set +a

PYTHON="${PYTHON:-python3}"
exec "$PYTHON" -m app.main "$@"
