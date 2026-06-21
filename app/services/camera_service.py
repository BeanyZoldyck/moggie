from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any, Callable

from app.config import MoggieConfig
from app.core.worker import ManagedWorker


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
        camera_backend: str = "opencv",
        camera_width: int,
        camera_height: int,
        camera_fps: int = 30,
        camera_gain: float = 1.0,
        camera_brightness: int = 0,
        cv_width: int,
        cv_height: int,
        retry_interval_seconds: int = 3,
        qnx_camera_grabber: Path = Path("./moggi_camgrab"),
        qnx_camera_unit: int = 1,
        qnx_camera_decimate: int = 3,
        capture_factory: CaptureFactory | None = None,
        cv2_module: Any | None = None,
    ) -> None:
        self.camera_backend = camera_backend
        self.camera_index = camera_index
        self.camera_width = camera_width
        self.camera_height = camera_height
        self.camera_fps = max(1, camera_fps)
        self.camera_gain = max(0.2, min(4.0, camera_gain))
        self.camera_brightness = max(-100, min(100, camera_brightness))
        self.cv_width = cv_width
        self.cv_height = cv_height
        self.retry_interval_seconds = retry_interval_seconds
        self.qnx_camera_grabber = qnx_camera_grabber
        self.qnx_camera_unit = qnx_camera_unit
        self.qnx_camera_decimate = qnx_camera_decimate
        self._capture_factory = capture_factory
        self._capture: Any | None = None
        self._cv2: Any | None = cv2_module
        self._latest_frame: CameraFrame | None = None
        self._lock = Lock()
        self._worker = _CameraWorker(self)
        self._running = False
        self._diagnostic = "Camera has not been started."
        self._next_retry_at = 0.0

    @classmethod
    def from_config(cls, config: MoggieConfig) -> CameraService:
        return cls(
            config.camera_index,
            camera_backend=config.camera_backend,
            camera_width=config.camera_width,
            camera_height=config.camera_height,
            camera_fps=config.camera_fps,
            camera_gain=config.camera_gain,
            camera_brightness=config.camera_brightness,
            cv_width=config.cv_width,
            cv_height=config.cv_height,
            retry_interval_seconds=config.camera_retry_seconds,
            qnx_camera_grabber=config.qnx_camera_grabber,
            qnx_camera_unit=config.qnx_camera_unit,
            qnx_camera_decimate=config.qnx_camera_decimate,
        )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_available(self) -> bool:
        if self.camera_backend == "qnx":
            return self._capture is not None and self._running
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
        if self.camera_backend == "qnx":
            self._start_qnx()
        else:
            self._start_opencv()
        if self._running:
            self._worker.start()

    def poll(self) -> CameraFrame | None:
        if self._capture is None and monotonic() >= self._next_retry_at:
            self.start()
        with self._lock:
            return self._latest_frame

    def latest_display_frame(self) -> Any | None:
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.display_bgr.copy()

    def latest_cv_frame(self) -> Any | None:
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.cv_bgr.copy()

    def snapshot(self) -> CameraFrame | None:
        with self._lock:
            if self._latest_frame is None:
                return None
            return CameraFrame(
                display_bgr=self._latest_frame.display_bgr.copy(),
                cv_bgr=self._latest_frame.cv_bgr.copy(),
                captured_at=self._latest_frame.captured_at,
            )

    def stop(self) -> None:
        self._running = False
        self._worker.stop()
        self._stop_capture()
        self._diagnostic = "Camera stopped."

    def _start_opencv(self) -> None:
        if not self._ensure_cv2("Camera index"):
            return

        cv2 = self._cv2
        factory = self._capture_factory or cv2.VideoCapture
        capture = factory(self.camera_index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.camera_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.camera_height)
        fps_prop = getattr(cv2, "CAP_PROP_FPS", None)
        if fps_prop is not None:
            capture.set(fps_prop, self.camera_fps)
        buffer_prop = getattr(cv2, "CAP_PROP_BUFFERSIZE", None)
        if buffer_prop is not None:
            capture.set(buffer_prop, 1)

        if not capture.isOpened():
            capture.release()
            self._diagnostic = (
                f"Camera index {self.camera_index} could not be opened. "
                f"Retrying every {self.retry_interval_seconds}s."
            )
            self._next_retry_at = monotonic() + self.retry_interval_seconds
            return

        self._capture = capture
        self._running = True
        self._next_retry_at = 0.0
        self._diagnostic = f"Camera index {self.camera_index} is open."
        self._read_frame()

    def _start_qnx(self) -> None:
        try:
            from app.services.qnx_camera_backend import QnxCamera, QnxCameraConfig
        except ImportError as exc:
            self._diagnostic = f"QNX camera backend unavailable: {exc}"
            self._next_retry_at = monotonic() + self.retry_interval_seconds
            return
        if not self._ensure_cv2("QNX camera"):
            return

        camera = QnxCamera(
            QnxCameraConfig(
                width=self.camera_width,
                height=self.camera_height,
                grabber=self.qnx_camera_grabber,
                unit=self.qnx_camera_unit,
                decimate=self.qnx_camera_decimate,
            )
        )
        try:
            camera.start()
        except (FileNotFoundError, OSError, RuntimeError) as exc:
            self._diagnostic = (
                f"QNX camera unit {self.qnx_camera_unit} could not start: {exc}. "
                f"Retrying every {self.retry_interval_seconds}s."
            )
            self._next_retry_at = monotonic() + self.retry_interval_seconds
            return

        self._capture = camera
        self._running = True
        self._next_retry_at = 0.0
        self._diagnostic = f"QNX camera unit {self.qnx_camera_unit} is open."
        self._read_frame(read_timeout=2.0)

    def _read_frame(self, *, read_timeout: float = 0.05) -> CameraFrame | None:
        if not self._running or self._capture is None:
            with self._lock:
                return self._latest_frame

        if self.camera_backend == "qnx":
            return self._read_qnx_frame(read_timeout=read_timeout)
        return self._read_opencv_frame()

    def _read_opencv_frame(self) -> CameraFrame | None:
        ok, frame = self._capture.read()
        if not ok or frame is None:
            self._diagnostic = (
                f"Camera index {self.camera_index} opened but did not return a frame. "
                "Keeping the last good frame."
            )
            with self._lock:
                return self._latest_frame

        latest = self._build_frame(frame)
        self._diagnostic = (
            f"Camera index {self.camera_index} streaming "
            f"{self.camera_width}x{self.camera_height}@{self.camera_fps}."
        )
        return latest

    def _read_qnx_frame(self, *, read_timeout: float) -> CameraFrame | None:
        try:
            frame = self._capture.read(timeout=read_timeout)
        except TimeoutError:
            self._diagnostic = (
                f"QNX camera unit {self.qnx_camera_unit} is open but no new frame is ready. "
                "Keeping the last good frame."
            )
            with self._lock:
                return self._latest_frame
        except (OSError, RuntimeError, ValueError) as exc:
            self._diagnostic = (
                f"QNX camera unit {self.qnx_camera_unit} stopped streaming: {exc}. "
                f"Retrying every {self.retry_interval_seconds}s."
            )
            self._running = False
            self._stop_capture()
            self._next_retry_at = monotonic() + self.retry_interval_seconds
            with self._lock:
                return self._latest_frame

        latest = self._build_frame(frame)
        self._diagnostic = (
            f"QNX camera unit {self.qnx_camera_unit} streaming "
            f"{self.camera_width}x{self.camera_height}@{self.camera_fps}."
        )
        return latest

    def _build_frame(self, frame: Any) -> CameraFrame:
        frame = self._adjust_frame(frame)
        display_frame = self._resize(frame, self.camera_width, self.camera_height)
        if hasattr(self._cv2, "flip"):
            display_frame = self._cv2.flip(display_frame, 1)
        cv_frame = self._resize(display_frame, self.cv_width, self.cv_height)
        latest = CameraFrame(
            display_bgr=display_frame,
            cv_bgr=cv_frame,
            captured_at=monotonic(),
        )
        with self._lock:
            self._latest_frame = latest
        return latest

    def _adjust_frame(self, frame: Any) -> Any:
        if self.camera_gain == 1.0 and self.camera_brightness == 0:
            return frame
        if self._cv2 is None or not hasattr(self._cv2, "convertScaleAbs"):
            return frame
        return self._cv2.convertScaleAbs(frame, alpha=self.camera_gain, beta=self.camera_brightness)

    def _stop_capture(self) -> None:
        if self._capture is None:
            return
        if hasattr(self._capture, "release"):
            self._capture.release()
        elif hasattr(self._capture, "close"):
            self._capture.close()
        elif hasattr(self._capture, "stop"):
            self._capture.stop()
        self._capture = None

    def _ensure_cv2(self, label: str) -> bool:
        if self._cv2 is not None:
            return True
        try:
            import cv2
        except ImportError:
            self._diagnostic = f"{label} unavailable: OpenCV is not installed."
            self._next_retry_at = monotonic() + self.retry_interval_seconds
            return False
        self._cv2 = cv2
        return True

    def _resize(self, frame: Any, width: int, height: int) -> Any:
        if frame.shape[1] == width and frame.shape[0] == height:
            return frame.copy()
        if self._cv2 is None:
            raise RuntimeError("CameraService cannot resize frames before OpenCV is loaded.")
        return self._cv2.resize(frame, (width, height), interpolation=self._cv2.INTER_AREA)


class _CameraWorker(ManagedWorker):
    def __init__(self, service: CameraService) -> None:
        super().__init__(name="moggie-camera-worker")
        self.service = service

    def run(self) -> None:
        interval_seconds = 1.0 / self.service.camera_fps
        while not self.should_stop:
            started_at = monotonic()
            self.service._read_frame()
            elapsed = monotonic() - started_at
            self.wait(max(0.001, interval_seconds - elapsed))
