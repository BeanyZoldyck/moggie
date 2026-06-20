from __future__ import annotations

from typing import Any


class MockImageGenerationClient:
    async def generate_caricature(self, image_bytes: bytes, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"status": "mocked", "prompt": prompt, "metadata": metadata, "bytes": len(image_bytes)}
