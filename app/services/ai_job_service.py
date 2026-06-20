from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any

from app.core.app_event import EVENT_AI_JOB_UPDATE, AppEvent, ai_job_update_payload
from app.core.event_bus import EventBus
from app.core.worker import ManagedWorker
from app.util.ids import new_id


AIJobHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class AIJob:
    id: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


class AIJobService:
    def __init__(self, *, event_bus: EventBus, handler: AIJobHandler | None = None) -> None:
        self.event_bus = event_bus
        self.handler = handler or self._default_handler
        self._jobs: Queue[AIJob] = Queue()
        self._worker = _AIJobWorker(self)

    @property
    def is_running(self) -> bool:
        return self._worker.is_running

    def start(self) -> None:
        self._worker.start()

    def stop(self) -> None:
        self._worker.stop()

    def submit(self, kind: str, payload: dict[str, Any] | None = None) -> str:
        job = AIJob(id=new_id("ai"), kind=kind, payload=payload or {})
        self._jobs.put(job)
        self._publish(job, "queued")
        return job.id

    def _publish(self, job: AIJob, status: str, **metadata: Any) -> None:
        self.event_bus.publish(
            AppEvent.create(
                EVENT_AI_JOB_UPDATE,
                payload=ai_job_update_payload(job.id, status, kind=job.kind, **metadata),
            )
        )

    def _default_handler(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"result": payload}


class _AIJobWorker(ManagedWorker):
    def __init__(self, service: AIJobService) -> None:
        super().__init__(name="moggie-ai-job-worker")
        self.service = service

    def run(self) -> None:
        while not self.should_stop:
            try:
                job = self.service._jobs.get(timeout=0.05)
            except Empty:
                continue
            self.service._publish(job, "running")
            try:
                result = self.service.handler(job.payload)
            except Exception as exc:
                self.service._publish(job, "failed", error=str(exc))
            else:
                self.service._publish(job, "complete", result=result)
            finally:
                self.service._jobs.task_done()
