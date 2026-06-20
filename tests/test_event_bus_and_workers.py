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
                    and event.payload["status"] == "complete"
                    for event in drained
                ),
            )
        finally:
            service.stop()

        statuses = [event.payload["status"] for event in events if event.type == EVENT_AI_JOB_UPDATE]
        self.assertIn("queued", statuses)
        self.assertIn("running", statuses)
        self.assertIn("complete", statuses)
        self.assertFalse(service.is_running)

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


if __name__ == "__main__":
    unittest.main()
