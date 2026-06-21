#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from time import monotonic, sleep

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_config
from app.cv.face_detection import FaceDetectionService
from app.cv.hand_landmarks import HandLandmarkService
from app.services.camera_service import CameraService


def _module_version(name: str) -> str:
    try:
        module = __import__(name)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return str(getattr(module, "__version__", "installed"))


def main() -> int:
    config = load_config()
    print(f"Python: {sys.executable}")
    print(f"OpenCV: {_module_version('cv2')}")
    print(f"MediaPipe: {_module_version('mediapipe')}")
    print(
        "Config: "
        f"camera_backend={config.camera_backend} camera_index={config.camera_index} "
        f"cv={config.cv_width}x{config.cv_height}@{config.cv_fps} "
        f"hand_backend={config.hand_tracking_backend} "
        f"face_backend={config.face_tracking_backend} "
        f"face_enabled={config.cv_enable_face_detection}"
    )

    camera = CameraService.from_config(config)
    hands = HandLandmarkService(
        max_hands=config.sixty_seven_max_hands,
        min_confidence=config.sixty_seven_min_confidence,
        split_x=config.zone_split_x,
        backend=config.hand_tracking_backend,
    )
    faces = FaceDetectionService(backend=config.face_tracking_backend)

    camera.start()
    hands.start()
    print(f"Camera: {camera.diagnostic_message}")
    print(f"Hands: {hands.diagnostic}")

    try:
        if not camera.is_available:
            return 1

        deadline = monotonic() + 5.0
        best_hand_count = 0
        best_face_count = 0
        sampled = 0
        while monotonic() < deadline:
            snapshot = camera.snapshot() or camera.poll()
            if snapshot is None:
                sleep(0.1)
                continue
            hand_detections = hands.detect(snapshot.cv_bgr)
            face_detections = faces.detect(snapshot.cv_bgr) if config.cv_enable_face_detection else []
            best_hand_count = max(best_hand_count, len(hand_detections))
            best_face_count = max(best_face_count, len(face_detections))
            sampled += 1
            print(
                f"Frame {sampled}: hands={len(hand_detections)} "
                f"faces={len(face_detections)} camera='{camera.diagnostic_message}'"
            )
            sleep(max(0.02, 1.0 / config.cv_fps))

        print(f"Best: hands={best_hand_count} faces={best_face_count}")
        if best_hand_count == 0 or (config.cv_enable_face_detection and best_face_count == 0):
            return 2
        return 0
    finally:
        faces.stop()
        hands.stop()
        camera.stop()


if __name__ == "__main__":
    raise SystemExit(main())
