from __future__ import annotations

import unittest
from unittest.mock import patch

from app.cv.hand_landmarks import HandLandmarkService


class _BrokenMediaPipe:
    class solutions:
        class hands:
            class Hands:
                def __init__(self, *args: object, **kwargs: object) -> None:
                    raise RuntimeError("graph unavailable")


class _WorkingFallback:
    available = False
    diagnostic = "fallback not started"

    def start(self) -> None:
        self.available = True
        self.diagnostic = "fallback started"

    def stop(self) -> None:
        self.available = False


class HandLandmarkServiceTests(unittest.TestCase):
    def test_auto_backend_falls_back_when_mediapipe_is_not_installed(self) -> None:
        service = HandLandmarkService(backend="auto")
        service._fallback = _WorkingFallback()

        with patch("app.cv.hand_landmarks.import_mediapipe", side_effect=ImportError):
            service.start()

        self.assertTrue(service.available)
        self.assertTrue(service._use_fallback)
        self.assertFalse(service._load_failed)
        self.assertIn("MediaPipe is not installed", service.diagnostic)
        self.assertIn("fallback started", service.diagnostic)

    def test_auto_backend_falls_back_when_mediapipe_hands_fails_to_start(self) -> None:
        service = HandLandmarkService(backend="auto", mediapipe_module=_BrokenMediaPipe())
        service._fallback = _WorkingFallback()

        service.start()

        self.assertTrue(service.available)
        self.assertTrue(service._use_fallback)
        self.assertFalse(service._load_failed)
        self.assertIn("MediaPipe Hands failed to start", service.diagnostic)
        self.assertIn("fallback started", service.diagnostic)

    def test_mediapipe_backend_does_not_fall_back_to_blob_detection(self) -> None:
        service = HandLandmarkService(backend="mediapipe")

        with patch("app.cv.hand_landmarks.import_mediapipe", side_effect=ImportError):
            service.start()

        self.assertFalse(service.available)
        self.assertFalse(service._use_fallback)
        self.assertTrue(service._load_failed)
        self.assertIn("MediaPipe is not installed", service.diagnostic)

    def test_mediapipe_hands_start_failure_does_not_fall_back_to_blob_detection(self) -> None:
        service = HandLandmarkService(backend="mediapipe", mediapipe_module=_BrokenMediaPipe())

        service.start()

        self.assertFalse(service.available)
        self.assertFalse(service._use_fallback)
        self.assertTrue(service._load_failed)
        self.assertIn("MediaPipe Hands failed to start", service.diagnostic)


if __name__ == "__main__":
    unittest.main()
