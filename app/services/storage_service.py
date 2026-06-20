from __future__ import annotations

from pathlib import Path


class StorageService:
    def __init__(self, mode: str, media_dir: Path) -> None:
        self.mode = mode
        self.media_dir = media_dir

    def ensure_ready(self) -> None:
        if self.mode in {"local", "usb"}:
            self.media_dir.mkdir(parents=True, exist_ok=True)
