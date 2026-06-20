from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


AIJobStatus = Literal["queued", "running", "succeeded", "failed", "timed_out", "skipped"]


@dataclass(frozen=True)
class AIJobResult:
    provider: str
    status: AIJobStatus
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class ImageGenerationClient(Protocol):
    async def generate_caricature(self, image_bytes: bytes, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        ...


class VideoGenerationClient(Protocol):
    async def generate_video(self, image_url: str, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        ...


class VisionValidationClient(Protocol):
    async def classify_expression(self, image_bytes: bytes, expression: str) -> dict[str, Any]:
        ...


class TextGenerationClient(Protocol):
    async def generate_label(self, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        ...
