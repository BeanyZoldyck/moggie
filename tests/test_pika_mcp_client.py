from __future__ import annotations

import asyncio
import unittest
from typing import Any

from app.ai.pika_mcp_client import PikaMCPClient


class FakePikaTransport:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def request(self, url: str, payload: dict[str, Any], token: str, *, timeout: float) -> dict[str, Any]:
        self.requests.append({"url": url, "payload": payload, "token": token, "timeout": timeout})
        method = payload["method"]
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": payload["id"], "result": {"capabilities": {"tools": {}}}}
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "tools": [
                        {
                            "name": "upload_asset",
                            "inputSchema": {
                                "properties": {
                                    "filename": {"type": "string"},
                                    "mime_type": {"type": "string"},
                                    "size_bytes": {"type": "integer"},
                                    "ttl_s": {"type": "integer"},
                                },
                                "required": ["filename", "mime_type", "size_bytes"],
                            },
                        },
                        {
                            "name": "generate_reference_video",
                            "inputSchema": {
                                "properties": {
                                    "prompt": {"type": "string"},
                                    "reference_images": {"type": "array"},
                                    "provider": {"enum": ["kling", "seedance", "minimax"]},
                                    "resolution": {"enum": ["480p", "720p", "1080p"]},
                                    "duration": {"type": "integer"},
                                    "aspect_ratio": {"enum": ["16:9", "9:16", "auto"]},
                                    "quality_mode": {"enum": ["std", "pro", "4k"]},
                                    "sound": {"type": "boolean"},
                                },
                                "required": ["prompt"],
                            },
                        },
                    ]
                },
            }
        if method == "tools/call":
            name = payload["params"]["name"]
            if name == "upload_asset":
                return {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "presigned_url": "https://upload.pika.test/put",
                        "public_url": "https://cdn.pika.test/source.jpg",
                    },
                }
            if name == "generate_reference_video":
                return {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"video_url": "https://cdn.pika.test/replay.mp4"},
                }
        raise AssertionError(payload)


class RecordingPikaMCPClient(PikaMCPClient):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.uploads: list[dict[str, Any]] = []

    def _put_bytes(self, url: str, body: bytes, content_type: str) -> None:
        self.uploads.append({"url": url, "body": body, "content_type": content_type})


class PikaMCPClientTests(unittest.TestCase):
    def test_generate_video_from_image_uploads_asset_then_generates_reference_video(self) -> None:
        transport = FakePikaTransport()
        client = RecordingPikaMCPClient(
            mcp_url="https://mcp.pika.test/api/mcp",
            bearer_token="token",
            timeout_seconds=20,
            transport=transport,
        )

        result = asyncio.run(
            client.generate_video_from_image(
                b"jpeg-bytes",
                "image/jpeg",
                "make a viral replay",
                {"display_name": "Ada", "duration": 5},
            )
        )

        self.assertEqual(result["video_url"], "https://cdn.pika.test/replay.mp4")
        self.assertEqual(client.uploads, [{"url": "https://upload.pika.test/put", "body": b"jpeg-bytes", "content_type": "image/jpeg"}])
        tool_calls = [request["payload"]["params"] for request in transport.requests if request["payload"]["method"] == "tools/call"]
        self.assertEqual(tool_calls[0]["name"], "upload_asset")
        self.assertEqual(tool_calls[0]["arguments"]["mime_type"], "image/jpeg")
        self.assertEqual(tool_calls[0]["arguments"]["size_bytes"], len(b"jpeg-bytes"))
        self.assertEqual(tool_calls[1]["name"], "generate_reference_video")
        self.assertEqual(tool_calls[1]["arguments"]["prompt"], "make a viral replay")
        self.assertEqual(tool_calls[1]["arguments"]["reference_images"], ["https://cdn.pika.test/source.jpg"])
        self.assertEqual(tool_calls[1]["arguments"]["provider"], "seedance")


if __name__ == "__main__":
    unittest.main()
