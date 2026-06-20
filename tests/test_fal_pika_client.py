from __future__ import annotations

import asyncio
import unittest
from typing import Any

from app.ai.fal_pika_client import FalPikaClient, FalPikaError


class FakeFalPikaClient(FalPikaClient):
    def __init__(self, *, statuses: list[dict[str, Any]], result: dict[str, Any]) -> None:
        self.status_events: list[tuple[str, str, dict[str, Any]]] = []
        super().__init__(
            api_key="test-key",
            model="fal-ai/pika/v2.2/image-to-video",
            timeout_seconds=2,
            poll_interval_seconds=0.01,
            on_status=self._record_status,
        )
        self.statuses = statuses
        self.result = result
        self.submitted_payloads: list[dict[str, Any]] = []

    def _record_status(self, job_id: str, status: str, metadata: dict[str, Any]) -> None:
        self.status_events.append((job_id, status, metadata))

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.submitted_payloads.append(payload)
        return {
            "request_id": "req_123",
            "status_url": "https://queue.fal.run/status",
            "response_url": "https://queue.fal.run/response",
        }

    def _get_json(self, url: str) -> dict[str, Any]:
        if self.statuses:
            return self.statuses.pop(0)
        return {"status": "COMPLETED", "request_id": "req_123"}

    def _request_json(
        self,
        url: str,
        *,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if url == "https://queue.fal.run/response":
            return self.result
        return super()._request_json(url, method=method, payload=payload)


class FalPikaClientTests(unittest.TestCase):
    def test_generate_video_submits_queue_job_and_returns_video_url(self) -> None:
        client = FakeFalPikaClient(
            statuses=[
                {"status": "IN_QUEUE", "request_id": "req_123", "queue_position": 1},
                {"status": "IN_PROGRESS", "request_id": "req_123"},
                {"status": "COMPLETED", "request_id": "req_123", "metrics": {"inference_time": 3.4}},
            ],
            result={"video": {"url": "https://v3.fal.media/files/video.mp4"}},
        )

        result = asyncio.run(
            client.generate_video(
                "https://example.com/source.png",
                "Arcade victory animation",
                {
                    "job_id": "ai_123",
                    "kind": "mog_mirror.victory_video",
                    "duration": 5,
                    "resolution": "720p",
                    "display_name": "Mina",
                },
            )
        )

        self.assertEqual(result["provider"], "fal")
        self.assertEqual(result["uri"], "https://v3.fal.media/files/video.mp4")
        self.assertEqual(result["request_id"], "req_123")
        self.assertEqual(client.submitted_payloads[0]["image_url"], "https://example.com/source.png")
        self.assertEqual(client.submitted_payloads[0]["prompt"], "Arcade victory animation")
        self.assertEqual(client.submitted_payloads[0]["duration"], 5)
        self.assertEqual(client.submitted_payloads[0]["resolution"], "720p")
        statuses = [status for _, status, _ in client.status_events]
        self.assertEqual(statuses, ["queued", "queued", "running", "running"])
        self.assertTrue(all(event[2]["request_id"] == "req_123" for event in client.status_events))

    def test_missing_image_url_fails_before_network_submit(self) -> None:
        client = FakeFalPikaClient(statuses=[], result={})

        with self.assertRaises(FalPikaError):
            asyncio.run(client.generate_video("", "prompt", {"job_id": "ai_123"}))

        self.assertEqual(client.submitted_payloads, [])


if __name__ == "__main__":
    unittest.main()
