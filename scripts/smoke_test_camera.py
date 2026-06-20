#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_config
from app.services.camera_service import CameraService


def main() -> int:
    config = load_config()
    camera = CameraService.from_config(config)
    camera.start()
    try:
        if not camera.is_available:
            print(camera.diagnostic_message, file=sys.stderr)
            return 1
        snapshot = camera.snapshot() or camera.poll()
        if snapshot is None:
            print(camera.diagnostic_message, file=sys.stderr)
            return 1
        display_h, display_w = snapshot.display_bgr.shape[:2]
        cv_h, cv_w = snapshot.cv_bgr.shape[:2]
        print(
            f"Camera OK: index={config.camera_index} "
            f"display={display_w}x{display_h} cv={cv_w}x{cv_h}"
        )
        return 0
    finally:
        camera.stop()


if __name__ == "__main__":
    raise SystemExit(main())
