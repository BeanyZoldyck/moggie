from __future__ import annotations

import logging
import queue
import threading
from typing import Any

LOGGER = logging.getLogger(__name__)


class VoiceMicCapture:
    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        device: str | int | None = None,
        chunk_frames: int = 1024,
    ) -> None:
        self.sample_rate = sample_rate
        self.device = device if device not in ("", None) else None
        self.chunk_frames = chunk_frames
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=64)
        self._stream: Any | None = None
        self._lock = threading.Lock()
        self._running = False
        self._available = True

    @property
    def available(self) -> bool:
        return self._available

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            try:
                import sounddevice as sd
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Microphone capture unavailable: %s", exc)
                self._available = False
                return
            try:
                kwargs: dict[str, Any] = {
                    "samplerate": self.sample_rate,
                    "channels": 1,
                    "dtype": "int16",
                    "blocksize": self.chunk_frames,
                    "callback": self._on_audio,
                }
                if self.device is not None:
                    kwargs["device"] = self.device
                self._stream = sd.RawInputStream(**kwargs)
                self._stream.start()
                self._running = True
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Failed to start microphone: %s", exc)
                self._available = False
                self._stream = None

    def stop(self) -> None:
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            self._running = False
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break

    def drain(self) -> list[bytes]:
        chunks: list[bytes] = []
        while True:
            try:
                chunks.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return chunks

    def _on_audio(self, indata: Any, _frames: int, _time: Any, status: Any) -> None:
        if status:
            LOGGER.debug("Mic capture status: %s", status)
        try:
            self._queue.put_nowait(bytes(indata))
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(bytes(indata))
            except queue.Full:
                pass
