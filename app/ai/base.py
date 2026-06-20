from __future__ import annotations

from typing import Any, Protocol


class ImageGenerationClient(Protocol):
    async def generate_caricature(self, image_bytes: bytes, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        ...


class VideoGenerationClient(Protocol):
    async def generate_video(self, image_url: str, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        ...


class VisionValidationClient(Protocol):
    async def classify_expression(self, image_bytes: bytes, expression: str) -> dict[str, Any]:
        ...
