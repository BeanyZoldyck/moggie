from __future__ import annotations

import asyncio
from typing import Any


class MockAIClient:
    provider_name = "mock"

    def __init__(self, *, delay_seconds: float = 0.01) -> None:
        self.delay_seconds = max(0.0, delay_seconds)

    async def _simulate(self, metadata: dict[str, Any]) -> None:
        await asyncio.sleep(float(metadata.get("mock_delay_seconds", self.delay_seconds)))
        if metadata.get("mock_fail"):
            raise RuntimeError(str(metadata.get("mock_error", "mock AI job failed")))


class MockImageGenerationClient(MockAIClient):
    async def generate_caricature(self, image_bytes: bytes, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        await self._simulate(metadata)
        return {
            "provider": self.provider_name,
            "kind": "image",
            "uri": f"mock://image/{metadata.get('display_name', 'player')}",
            "prompt": prompt,
            "metadata": metadata,
            "bytes": len(image_bytes),
        }


class MockVideoGenerationClient(MockAIClient):
    async def generate_video(self, image_url: str, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        await self._simulate(metadata)
        return {
            "provider": self.provider_name,
            "kind": "video",
            "uri": f"mock://video/{metadata.get('display_name', 'player')}",
            "image_url": image_url,
            "prompt": prompt,
            "metadata": metadata,
        }


class MockVisionValidationClient(MockAIClient):
    async def classify_expression(self, image_bytes: bytes, expression: str) -> dict[str, Any]:
        metadata = {"expression": expression}
        await self._simulate(metadata)
        return {
            "provider": self.provider_name,
            "kind": "vision_validation",
            "expression": expression,
            "matched": True,
            "confidence": 0.92,
            "bytes": len(image_bytes),
        }


class MockTextGenerationClient(MockAIClient):
    async def generate_label(self, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        await self._simulate(metadata)
        return {
            "provider": self.provider_name,
            "kind": "text",
            "text": str(metadata.get("fallback_label") or "Certified Mog Energy"),
            "prompt": prompt,
            "metadata": metadata,
        }
