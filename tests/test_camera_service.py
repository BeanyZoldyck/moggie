from __future__ import annotations

import unittest

from app.services.camera_service import CameraService


class FakeFrame:
    def __init__(self, width: int, height: int, marker: int = 24) -> None:
        self.shape = (height, width, 3)
        self.marker = marker

    def copy(self) -> "FakeFrame":
        return FakeFrame(self.shape[1], self.shape[0], self.marker)


class FakeCv2:
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    INTER_AREA = 3

    def resize(self, frame: FakeFrame, size: tuple[int, int], interpolation: int) -> FakeFrame:
        return FakeFrame(size[0], size[1], frame.marker)


class FakeCapture:
    def __init__(self, opened: bool = True) -> None:
        self.opened = opened
        self.released = False
        self.set_calls: list[tuple[int, int]] = []
        self.read_count = 0

    def isOpened(self) -> bool:
        return self.opened

    def set(self, prop: int, value: int) -> None:
        self.set_calls.append((prop, value))

    def read(self) -> tuple[bool, FakeFrame]:
        self.read_count += 1
        return True, FakeFrame(640, 480)

    def release(self) -> None:
        self.released = True
        self.opened = False


class CameraServiceTests(unittest.TestCase):
    def test_start_opens_configured_camera_and_caches_display_and_cv_frames(self) -> None:
        fake = FakeCapture()
        service = CameraService(
            2,
            camera_width=640,
            camera_height=480,
            cv_width=320,
            cv_height=240,
            capture_factory=lambda index: fake,
            cv2_module=FakeCv2(),
        )

        service.start()
        snapshot = service.snapshot()

        self.assertTrue(service.is_available)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.display_bgr.shape, (480, 640, 3))
        self.assertEqual(snapshot.cv_bgr.shape, (240, 320, 3))
        self.assertIn("Camera index 2 streaming", service.diagnostic_message)

    def test_latest_frames_are_copies_for_game_snapshot_use(self) -> None:
        service = CameraService(
            0,
            camera_width=640,
            camera_height=480,
            cv_width=320,
            cv_height=240,
            capture_factory=lambda index: FakeCapture(),
            cv2_module=FakeCv2(),
        )

        service.start()
        first = service.latest_display_frame()
        second = service.latest_display_frame()

        self.assertIsNot(first, second)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)

    def test_failed_camera_open_sets_diagnostic_without_raising(self) -> None:
        service = CameraService(
            9,
            camera_width=640,
            camera_height=480,
            cv_width=320,
            cv_height=240,
            capture_factory=lambda index: FakeCapture(opened=False),
            cv2_module=FakeCv2(),
        )

        service.start()

        self.assertFalse(service.is_available)
        self.assertIn("Camera index 9 could not be opened", service.diagnostic_message)


if __name__ == "__main__":
    unittest.main()
