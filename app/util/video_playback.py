from __future__ import annotations

import logging
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.request import urlopen

LOGGER = logging.getLogger(__name__)

DownloadCallback = Callable[[Path | None], None]


def download_to_tempfile(url: str, *, timeout: float = 30.0) -> Path:
    """Download ``url`` to a temp .mp4 and return its path.

    OpenCV's VideoCapture is unreliable reading remote HTTP streams, so we land
    the clip on disk first. Caller owns cleanup of the returned file.
    """
    with urlopen(url, timeout=timeout) as response:  # noqa: S310 - trusted fal.media URL
        data = response.read()
    handle = tempfile.NamedTemporaryFile(prefix="moggie_avatar_", suffix=".mp4", delete=False)
    try:
        handle.write(data)
    finally:
        handle.close()
    return Path(handle.name)


def download_in_background(url: str, on_ready: DownloadCallback, *, timeout: float = 30.0) -> threading.Thread:
    """Download ``url`` off-thread; invoke ``on_ready(path)`` (or ``None`` on failure).

    The callback runs on the worker thread, so it must only hand the result to a
    thread-safe sink (e.g. a Queue) for the main loop to consume.
    """

    def _run() -> None:
        try:
            path = download_to_tempfile(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - report all failures as a None result
            LOGGER.warning("Avatar video download failed for %s: %s", url, exc)
            on_ready(None)
            return
        on_ready(path)

    thread = threading.Thread(target=_run, name="moggie-avatar-download", daemon=True)
    thread.start()
    return thread


class LoopingVideoPlayer:
    """Decode a local video file frame-by-frame, looping forever.

    ``advance(now_ms)`` paces playback to the clip's fps; ``current_frame_bgr()``
    returns the most recent BGR ndarray (the same format the camera service and
    CameraPreviewRenderer use), so the frame can be dropped straight into the
    existing preview pipeline.
    """

    def __init__(self, path: Path | str, *, cv2_module: Any | None = None) -> None:
        self._path = str(path)
        self._cv2 = cv2_module
        self._capture: Any | None = None
        self._frame: Any | None = None
        self._frame_interval_ms = 1000.0 / 30.0
        self._last_advance_ms: float | None = None
        self._open()

    def _load_cv2(self) -> Any | None:
        if self._cv2 is not None:
            return self._cv2
        try:
            import cv2
        except Exception:  # noqa: BLE001
            return None
        self._cv2 = cv2
        return cv2

    def _open(self) -> None:
        cv2 = self._load_cv2()
        if cv2 is None:
            return
        self._capture = cv2.VideoCapture(self._path)
        if not self._capture.isOpened():
            self._capture.release()
            self._capture = None
            return
        fps = float(self._capture.get(cv2.CAP_PROP_FPS) or 0.0)
        if fps > 1.0:
            self._frame_interval_ms = 1000.0 / fps
        self._read_next()

    def _read_next(self) -> None:
        cv2 = self._load_cv2()
        if cv2 is None or self._capture is None:
            return
        ok, frame = self._capture.read()
        if not ok:
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._capture.read()
        if ok:
            self._frame = frame

    def advance(self, now_ms: float) -> None:
        if self._capture is None:
            return
        if self._last_advance_ms is None:
            self._last_advance_ms = now_ms
            return
        if now_ms - self._last_advance_ms < self._frame_interval_ms:
            return
        self._last_advance_ms = now_ms
        self._read_next()

    def current_frame_bgr(self) -> Any | None:
        return self._frame

    @property
    def is_ready(self) -> bool:
        return self._frame is not None

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
