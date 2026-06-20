#!/usr/bin/env python3
from __future__ import annotations

import sys

from app.config import load_config


def main() -> int:
    try:
        import cv2
    except ImportError:
        print("opencv-python is not installed; install project dependencies first.", file=sys.stderr)
        return 2

    config = load_config()
    capture = cv2.VideoCapture(config.camera_index)
    try:
        if not capture.isOpened():
            print(f"Camera index {config.camera_index} could not be opened.", file=sys.stderr)
            return 1
        ok, frame = capture.read()
        if not ok or frame is None:
            print("Camera opened but did not return a frame.", file=sys.stderr)
            return 1
        height, width = frame.shape[:2]
        print(f"Camera OK: {width}x{height}")
        return 0
    finally:
        capture.release()


if __name__ == "__main__":
    raise SystemExit(main())
