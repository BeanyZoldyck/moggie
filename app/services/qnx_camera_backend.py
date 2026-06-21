"""QNX CamAPI camera bridge for Raspberry Pi Camera Module 3.

QNX does not expose the Pi Camera Module 3 through rpicam/libcamera or a useful
OpenCV VideoCapture backend. The native ``moggi_camgrab`` helper owns the CamAPI
viewfinder path and streams tightly packed NV12 frames to stdout. This module
keeps the latest streamed frame and converts it to BGR for the rest of Moggie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import struct
import subprocess
import threading
from typing import Any, Iterable


_MAGIC = b"MGF1"
_HEADER = struct.Struct("<4sIII")


@dataclass(frozen=True)
class QnxCameraConfig:
    width: int = 640
    height: int = 480
    framerate: int = 30
    grabber: Path = Path("./moggi_camgrab")
    unit: int = 1
    decimate: int = 3
    extra_args: tuple[str, ...] = field(default_factory=tuple)

    def command(self) -> list[str]:
        return [
            self._grabber_command_path(),
            "stream",
            str(self.decimate),
            str(self.unit),
            *self.extra_args,
        ]

    def _grabber_command_path(self) -> str:
        if self.grabber.is_absolute() or self.grabber.parent != Path("."):
            return str(self.grabber)
        return f".{os.sep}{self.grabber}"


class QnxCamera:
    def __init__(self, config: QnxCameraConfig | None = None) -> None:
        self.config = config or QnxCameraConfig()
        self.process: subprocess.Popen[bytes] | None = None
        self._latest: tuple[int, int, bytes] | None = None
        self._lock = threading.Lock()
        self._frame_ready = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_lines: list[str] = []
        self._stop = threading.Event()

    @property
    def stderr_tail(self) -> str:
        return "\n".join(self._stderr_lines[-20:])

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        if not self.config.grabber.exists():
            raise FileNotFoundError(
                f"{self.config.grabber} not found. Build it with: "
                "gcc native/moggi_camgrab.c -o moggi_camgrab -lcamapi"
            )

        self._stop.clear()
        self._frame_ready.clear()
        self.process = subprocess.Popen(
            self.config.command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def read(self, timeout: float = 2.0) -> Any:
        if not self.process or self.process.poll() is not None:
            raise RuntimeError(f"moggi_camgrab is not running. stderr:\n{self.stderr_tail}")
        if not self._frame_ready.wait(timeout):
            raise TimeoutError(f"Timed out waiting for QNX camera frame. stderr:\n{self.stderr_tail}")

        with self._lock:
            latest = self._latest
        if latest is None:
            raise TimeoutError("No QNX camera frame is available.")

        import cv2
        import numpy as np

        width, height, data = latest
        yuv = np.frombuffer(data, dtype=np.uint8).reshape((height * 3 // 2, width))
        bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_NV12)
        if (width, height) != (self.config.width, self.config.height):
            bgr = cv2.resize(
                bgr,
                (self.config.width, self.config.height),
                interpolation=cv2.INTER_AREA,
            )
        return bgr

    def frames(self, timeout: float = 2.0) -> Iterable[Any]:
        while True:
            yield self.read(timeout=timeout)

    def close(self) -> None:
        self._stop.set()
        proc = self.process
        self.process = None
        if not proc:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)

    def stop(self) -> None:
        self.close()

    def __enter__(self) -> "QnxCamera":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def _read_exact(self, fd: int, size: int) -> bytes | None:
        data = bytearray()
        while len(data) < size and not self._stop.is_set():
            try:
                chunk = os.read(fd, size - len(data))
            except OSError:
                return None
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data) if len(data) == size else None

    def _read_loop(self) -> None:
        proc = self.process
        if not proc or not proc.stdout:
            return
        fd = proc.stdout.fileno()
        while not self._stop.is_set():
            header = self._read_exact(fd, _HEADER.size)
            if header is None:
                break
            magic, width, height, data_len = _HEADER.unpack(header)
            if magic != _MAGIC:
                break
            data = self._read_exact(fd, data_len)
            if data is None:
                break
            with self._lock:
                self._latest = (width, height, data)
            self._frame_ready.set()

    def _drain_stderr(self) -> None:
        proc = self.process
        if not proc or not proc.stderr:
            return
        for raw in iter(proc.stderr.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                self._stderr_lines.append(line)
                if len(self._stderr_lines) > 100:
                    del self._stderr_lines[:50]
