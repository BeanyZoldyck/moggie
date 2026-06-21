from __future__ import annotations

import json
import logging
import tempfile
import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.config import MoggieConfig

LOGGER = logging.getLogger(__name__)


class VoiceService:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "aura-2-atlas-en",
        enabled: bool = True,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip() or "aura-2-atlas-en"
        self.enabled = enabled and bool(self.api_key)
        self._queue: Queue[str] = Queue()
        self._worker = threading.Thread(target=self._run, name="moggie-voice-worker", daemon=True)
        self._running = False
        self._mixer_ready = False

    @classmethod
    def from_config(cls, config: MoggieConfig) -> "VoiceService":
        return cls(
            api_key=config.deepgram_api_key,
            model=config.deepgram_voice_model,
            enabled=config.enable_voice,
        )

    def start(self) -> None:
        if not self.enabled or self._running:
            return
        self._init_mixer()
        self._running = True
        self._worker.start()

    def stop(self) -> None:
        self._running = False
        self._queue.put("")

    def speak(self, text: str) -> None:
        clean = text.strip()
        if not self.enabled or not clean:
            return
        self._queue.put(clean)

    def _init_mixer(self) -> None:
        if self._mixer_ready:
            return
        try:
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050)
            self._mixer_ready = True
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Voice playback unavailable (pygame mixer): %s", exc)
            self.enabled = False

    def _run(self) -> None:
        while self._running:
            try:
                text = self._queue.get(timeout=0.1)
            except Empty:
                continue
            if not text:
                continue
            try:
                audio_path = self._synthesize(text)
                self._play(audio_path)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Voice line failed for %r: %s", text, exc)

    def _synthesize(self, text: str) -> Path:
        model = quote(self.model, safe="")
        url = f"https://api.deepgram.com/v1/speak?model={model}&encoding=mp3"
        payload = json.dumps({"text": text}).encode("utf-8")
        request = Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
        )
        try:
            with urlopen(request, timeout=20.0) as response:
                audio = response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Deepgram TTS HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Deepgram TTS network error: {exc.reason}") from exc

        handle = tempfile.NamedTemporaryFile(prefix="moggie_voice_", suffix=".mp3", delete=False)
        try:
            handle.write(audio)
        finally:
            handle.close()
        return Path(handle.name)

    def _play(self, path: Path) -> None:
        if not self._mixer_ready:
            return
        import pygame

        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(50)
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
