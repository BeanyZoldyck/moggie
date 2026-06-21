from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class VoiceAgentAudioPlayer:
    def __init__(self) -> None:
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._mixer_ready = False
        self._playing = False

    def append(self, chunk: bytes) -> None:
        if not chunk:
            return
        with self._lock:
            self._buffer.extend(chunk)

    def flush_and_play(self) -> None:
        with self._lock:
            data = bytes(self._buffer)
            self._buffer.clear()
        if not data:
            return
        self._play_bytes(data)

    def stop(self) -> None:
        if not self._mixer_ready:
            return
        try:
            import pygame

            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except Exception:
            pass
        with self._lock:
            self._buffer.clear()
        self._playing = False

    def _init_mixer(self) -> None:
        if self._mixer_ready:
            return
        try:
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050)
            self._mixer_ready = True
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Agent audio playback unavailable: %s", exc)

    def _play_bytes(self, data: bytes) -> None:
        self._init_mixer()
        if not self._mixer_ready:
            return
        import pygame

        handle = tempfile.NamedTemporaryFile(prefix="moggie_agent_", suffix=".mp3", delete=False)
        path = Path(handle.name)
        try:
            handle.write(data)
        finally:
            handle.close()
        try:
            self.stop()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            self._playing = True
            while pygame.mixer.music.get_busy():
                pygame.time.wait(50)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Agent audio playback failed: %s", exc)
        finally:
            self._playing = False
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
