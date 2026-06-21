from __future__ import annotations

import time
import unittest
from collections.abc import Callable

from app.core.app_event import (
    EVENT_AI_JOB_UPDATE,
    EVENT_CV_HAND_LANDMARKS,
    AppEvent,
    normalized_point,
)
from app.core.event_bus import EventBus
from app.ai.fal_pika_client import FalPikaClient
from app.ai.mock_clients import MockVideoGenerationClient
from app.ai.pika_mcp_client import PikaMCPClient
from app.config import load_config
from app.services.ai_job_service import AIJobService
from app.services.cv_service import CVService


class EventBusAndWorkerTests(unittest.TestCase):
    def test_event_bus_drains_events_published_from_worker_thread(self) -> None:
        bus = EventBus()
        service = CVService(event_bus=bus, cv_fps=30, mock_events=True)

        service.start()
        try:
            events = self._drain_until(bus, lambda drained: len(drained) >= 2)
        finally:
            service.stop()

        event_types = {event.type for event in events}
        self.assertIn(EVENT_CV_HAND_LANDMARKS, event_types)
        self.assertTrue(all(isinstance(event.timestamp_ms, int) for event in events))
        hand_event = next(event for event in events if event.type == EVENT_CV_HAND_LANDMARKS)
        self.assertEqual(hand_event.payload["zone_assignment"]["counts"], {"p1": 1, "p2": 1})
        self.assertEqual(hand_event.payload["hands"][0]["zone_assignment"]["source"], "palm_center")
        self.assertFalse(service.is_running)

    def test_latest_cv_state_tracks_most_recent_cv_payload(self) -> None:
        bus = EventBus()
        service = CVService(event_bus=bus)
        event = AppEvent.create(
            EVENT_CV_HAND_LANDMARKS,
            payload={
                "hands": [
                    {
                        "hand_id": "h1",
                        "palm_center": normalized_point(1.4, -0.2),
                        "landmarks": [normalized_point(0.5, 0.25)],
                    }
                ]
            },
        )

        service.publish(event)
        latest = service.latest_state()

        self.assertEqual(latest.timestamp_ms, event.timestamp_ms)
        self.assertEqual(latest.hand_landmarks["hands"][0]["palm_center"], {"x": 1.0, "y": 0.0})
        self.assertEqual(bus.drain(), [event])

    def test_ai_job_worker_emits_lifecycle_events_and_stops_cleanly(self) -> None:
        bus = EventBus()
        service = AIJobService(event_bus=bus, handler=lambda payload: {"echo": payload["value"]})

        service.start()
        try:
            job_id = service.submit("mock", {"value": 67})
            events = self._drain_until(
                bus,
                lambda drained: any(
                    event.type == EVENT_AI_JOB_UPDATE
                    and event.payload["job_id"] == job_id
                    and event.payload["status"] == "succeeded"
                    for event in drained
                ),
            )
        finally:
            service.stop()

        statuses = [event.payload["status"] for event in events if event.type == EVENT_AI_JOB_UPDATE]
        self.assertIn("queued", statuses)
        self.assertIn("running", statuses)
        self.assertIn("succeeded", statuses)
        self.assertFalse(service.is_running)

    def test_ai_job_worker_emits_failed_event_without_blocking(self) -> None:
        bus = EventBus()

        def fail(_: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("provider unavailable")

        service = AIJobService(event_bus=bus, handler=fail)

        service.start()
        try:
            job_id = service.submit("mock.fail", {})
            events = self._drain_until(
                bus,
                lambda drained: any(
                    event.type == EVENT_AI_JOB_UPDATE
                    and event.payload["job_id"] == job_id
                    and event.payload["status"] == "failed"
                    for event in drained
                ),
            )
        finally:
            service.stop()

        failed = next(event for event in events if event.payload.get("status") == "failed")
        self.assertEqual(failed.payload["metadata"]["error"], "provider unavailable")

    def test_ai_job_worker_times_out_slow_mock_jobs(self) -> None:
        bus = EventBus()
        service = AIJobService(event_bus=bus, timeout_seconds=0.01)

        service.start()
        try:
            job_id = service.submit("mog_mirror.caricature", {"mock_delay_seconds": 0.1})
            events = self._drain_until(
                bus,
                lambda drained: any(
                    event.type == EVENT_AI_JOB_UPDATE
                    and event.payload["job_id"] == job_id
                    and event.payload["status"] == "timed_out"
                    for event in drained
                ),
            )
        finally:
            service.stop()

        statuses = [event.payload["status"] for event in events if event.payload.get("job_id") == job_id]
        self.assertEqual(statuses[-1], "timed_out")

    def test_mock_ai_route_completes_without_network_access(self) -> None:
        bus = EventBus()
        service = AIJobService(event_bus=bus)

        service.start()
        try:
            job_id = service.submit("mog_mirror.caricature", {"display_name": "Ada"})
            events = self._drain_until(
                bus,
                lambda drained: any(
                    event.type == EVENT_AI_JOB_UPDATE
                    and event.payload["job_id"] == job_id
                    and event.payload["status"] == "succeeded"
                    for event in drained
                ),
            )
        finally:
            service.stop()

        succeeded = next(event for event in events if event.payload.get("status") == "succeeded")
        result = succeeded.payload["metadata"]["result"]
        self.assertEqual(result["provider"], "mock")
        self.assertEqual(result["kind"], "image")
        self.assertEqual(result["uri"], "mock://image/Ada")

    def test_midjourney_image_success_enqueues_pika_video_followup(self) -> None:
        bus = EventBus()
        video_client = RecordingVideoClient()
        service = AIJobService(
            event_bus=bus,
            image_client=PublicImageClient(),
            video_client=video_client,
            timeout_seconds=2,
        )

        service.start()
        try:
            service.submit(
                "mog_mirror.caricature",
                {
                    "display_name": "Ada",
                    "image_bytes": b"jpeg",
                    "request_pika_video": True,
                    "video_prompt": "make the win cinematic",
                },
            )
            service._jobs.join()
        finally:
            service.stop()

        events = [event.payload for event in bus.drain() if event.type == EVENT_AI_JOB_UPDATE]
        kinds = [event["metadata"].get("kind") for event in events]
        self.assertIn("mog_mirror.caricature", kinds)
        self.assertIn("mog_mirror.victory_video", kinds)
        self.assertEqual(video_client.calls[0]["image_url"], "https://cdn.midjourney.test/winner.png")
        self.assertEqual(video_client.calls[0]["prompt"], "make the win cinematic")

    def test_video_job_can_send_original_image_bytes_to_pika_client(self) -> None:
        bus = EventBus()
        video_client = RecordingDirectImageVideoClient()
        service = AIJobService(event_bus=bus, video_client=video_client, timeout_seconds=2)

        service.start()
        try:
            service.submit(
                "mog_mirror.victory_video",
                {
                    "image_bytes": b"jpeg",
                    "image_mime_type": "image/jpeg",
                    "prompt": "viral replay",
                },
            )
            service._jobs.join()
        finally:
            service.stop()

        self.assertEqual(video_client.calls[0]["image_bytes"], b"jpeg")
        self.assertEqual(video_client.calls[0]["image_mime_type"], "image/jpeg")
        self.assertEqual(video_client.calls[0]["prompt"], "viral replay")

    def test_ai_job_service_uses_fal_pika_client_only_when_enabled_and_configured(self) -> None:
        bus = EventBus()
        configured = AIJobService.from_config(
            load_config(
                {
                    "MOGGIE_ENABLE_PIKA": "true",
                    "MOGGIE_PIKA_PROVIDER": "fal",
                    "FAL_KEY": "test-key",
                    "MOGGIE_PIKA_MODEL": "fal-ai/pika/v2.2/image-to-video",
                }
            ),
            event_bus=bus,
        )
        fallback = AIJobService.from_config(load_config({"MOGGIE_ENABLE_PIKA": "true", "MOGGIE_PIKA_PROVIDER": "fal"}), event_bus=bus)

        self.assertIsInstance(configured.video_client, FalPikaClient)
        self.assertEqual(configured.video_client.model, "fal-ai/pika/v2.2/image-to-video")
        self.assertIsInstance(fallback.video_client, MockVideoGenerationClient)

    def test_ai_job_service_uses_pika_mcp_client_by_default_when_pika_enabled(self) -> None:
        bus = EventBus()
        configured = AIJobService.from_config(
            load_config(
                {
                    "MOGGIE_ENABLE_PIKA": "true",
                    "MOGGIE_PIKA_MCP_URL": "https://mcp.pika.test/api/mcp",
                    "MOGGIE_PIKA_MCP_BEARER_TOKEN": "token",
                    "MOGGIE_PIKA_MCP_GENERATION_TOOL": "generate_reference_video",
                }
            ),
            event_bus=bus,
        )

        self.assertIsInstance(configured.video_client, PikaMCPClient)
        self.assertEqual(configured.video_client.mcp_url, "https://mcp.pika.test/api/mcp")
        self.assertEqual(configured.video_client.generation_tool, "generate_reference_video")

    def _drain_until(
        self,
        bus: EventBus,
        done: Callable[[list[AppEvent]], bool],
        timeout_seconds: float = 1.0,
    ) -> list[AppEvent]:
        deadline = time.monotonic() + timeout_seconds
        drained: list[AppEvent] = []
        while time.monotonic() < deadline:
            drained.extend(bus.drain())
            if done(drained):
                return drained
            time.sleep(0.01)
        return drained


class PublicImageClient:
    async def generate_caricature(self, image_bytes: bytes, prompt: str, metadata: dict[str, object]) -> dict[str, object]:
        return {
            "provider": "midjourney",
            "kind": "image",
            "image_url": "https://cdn.midjourney.test/winner.png",
            "prompt": prompt,
            "bytes": len(image_bytes),
            "metadata": metadata,
        }


class RecordingVideoClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def generate_video(self, image_url: str, prompt: str, metadata: dict[str, object]) -> dict[str, object]:
        self.calls.append({"image_url": image_url, "prompt": prompt, "metadata": metadata})
        return {
            "provider": "pika",
            "kind": "video",
            "video_url": "https://cdn.pika.test/replay.mp4",
            "image_url": image_url,
            "prompt": prompt,
        }


class RecordingDirectImageVideoClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def generate_video(self, image_url: str, prompt: str, metadata: dict[str, object]) -> dict[str, object]:
        raise AssertionError("direct image path should be used")

    async def generate_video_from_image(
        self,
        image_bytes: bytes,
        image_mime_type: str,
        prompt: str,
        metadata: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "image_bytes": image_bytes,
                "image_mime_type": image_mime_type,
                "prompt": prompt,
                "metadata": metadata,
            }
        )
        return {
            "provider": "pika_mcp",
            "kind": "video",
            "video_url": "https://cdn.pika.test/replay.mp4",
        }


if __name__ == "__main__":
    unittest.main()
