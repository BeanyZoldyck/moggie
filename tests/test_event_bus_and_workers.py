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

    def test_ai_job_service_uses_fal_pika_client_only_when_enabled_and_configured(self) -> None:
        bus = EventBus()
        configured = AIJobService.from_config(
            load_config(
                {
                    "MOGGIE_ENABLE_PIKA": "true",
                    "FAL_KEY": "test-key",
                    "MOGGIE_PIKA_MODEL": "fal-ai/pika/v2.2/image-to-video",
                }
            ),
            event_bus=bus,
        )
        fallback = AIJobService.from_config(load_config({"MOGGIE_ENABLE_PIKA": "true"}), event_bus=bus)

        self.assertIsInstance(configured.video_client, FalPikaClient)
        self.assertEqual(configured.video_client.model, "fal-ai/pika/v2.2/image-to-video")
        self.assertIsInstance(fallback.video_client, MockVideoGenerationClient)

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


if __name__ == "__main__":
    unittest.main()
