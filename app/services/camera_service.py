from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable

from app.config import MoggieConfig


@dataclass(frozen=True)
class CameraFrame:
    display_bgr: Any
    cv_bgr: Any
    captured_at: float


CaptureFactory = Callable[[int], Any]


class CameraService:
    def __init__(
        self,
        camera_index: int,
        *,
        camera_width: int,
        camera_height: int,
        cv_width: int,
        cv_height: int,
        capture_factory: CaptureFactory | None = None,
        cv2_module: Any | None = None,
    ) -> None:
        self.camera_index = camera_index
        self.camera_width = camera_width
        self.camera_height = camera_height
        self.cv_width = cv_width
        self.cv_height = cv_height
        self._capture_factory = capture_factory
        self._capture: Any | None = None
        self._cv2: Any | None = cv2_module
        self._latest_frame: CameraFrame | None = None
        self._running = False
        self._diagnostic = "Camera has not been started."

    @classmethod
    def from_config(cls, config: MoggieConfig) -> CameraService:
        return cls(
            config.camera_index,
            camera_width=config.camera_width,
            camera_height=config.camera_height,
            cv_width=config.cv_width,
            cv_height=config.cv_height,
        )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_available(self) -> bool:
        return self._capture is not None and self._capture.isOpened()

    @property
    def has_frame(self) -> bool:
        return self._latest_frame is not None

    @property
    def diagnostic_message(self) -> str:
        return self._diagnostic

    def start(self) -> None:
        if self._capture is not None:
            return
        if self._cv2 is None:
            try:
                import cv2
            except ImportError:
                self._diagnostic = (
                    f"Camera index {self.camera_index} unavailable: "
                    "OpenCV is not installed."
                )
                return
            self._cv2 = cv2

        cv2 = self._cv2
        factory = self._capture_factory or cv2.VideoCapture
        capture = factory(self.camera_index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.camera_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.camera_height)

        if not capture.isOpened():
            capture.release()
            self._diagnostic = f"Camera index {self.camera_index} could not be opened."
            return

        self._capture = capture
        self._running = True
        self._diagnostic = f"Camera index {self.camera_index} is open."
        self.poll()

    def poll(self) -> CameraFrame | None:
        if not self._running or self._capture is None:
            return self._latest_frame

        ok, frame = self._capture.read()
        if not ok or frame is None:
            self._diagnostic = f"Camera index {self.camera_index} opened but did not return a frame."
            return self._latest_frame

        display_frame = self._resize(frame, self.camera_width, self.camera_height)
        cv_frame = self._resize(display_frame, self.cv_width, self.cv_height)
        self._latest_frame = CameraFrame(
            display_bgr=display_frame,
            cv_bgr=cv_frame,
            captured_at=monotonic(),
        )
        self._diagnostic = f"Camera index {self.camera_index} streaming {self.camera_width}x{self.camera_height}."
        return self._latest_frame

    def latest_display_frame(self) -> Any | None:
        if self._latest_frame is None:
            return None
        return self._latest_frame.display_bgr.copy()

    def latest_cv_frame(self) -> Any | None:
        if self._latest_frame is None:
            return None
        return self._latest_frame.cv_bgr.copy()

    def snapshot(self) -> CameraFrame | None:
        if self._latest_frame is None:
            return None
        return CameraFrame(
            display_bgr=self._latest_frame.display_bgr.copy(),
            cv_bgr=self._latest_frame.cv_bgr.copy(),
            captured_at=self._latest_frame.captured_at,
        )

    def stop(self) -> None:
        self._running = False
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._diagnostic = "Camera stopped."

    def _resize(self, frame: Any, width: int, height: int) -> Any:
        if frame.shape[1] == width and frame.shape[0] == height:
            return frame.copy()
        if self._cv2 is None:
            raise RuntimeError("CameraService cannot resize frames before OpenCV is loaded.")
        return self._cv2.resize(frame, (width, height), interpolation=self._cv2.INTER_AREA)
