from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any

from app.ai.base import (
    ImageGenerationClient,
    TextGenerationClient,
    VideoGenerationClient,
    VisionValidationClient,
)
from app.ai.fal_pika_client import FalPikaClient
from app.ai.mock_clients import (
    MockImageGenerationClient,
    MockTextGenerationClient,
    MockVideoGenerationClient,
    MockVisionValidationClient,
)
from app.config import MoggieConfig
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
    timeout_seconds: float | None = None


class AIJobService:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        handler: AIJobHandler | None = None,
        image_client: ImageGenerationClient | None = None,
        video_client: VideoGenerationClient | None = None,
        vision_client: VisionValidationClient | None = None,
        text_client: TextGenerationClient | None = None,
        timeout_seconds: float = 45,
    ) -> None:
        self.event_bus = event_bus
        self.handler = handler
        self.image_client = image_client or MockImageGenerationClient()
        self.video_client = video_client or MockVideoGenerationClient()
        self.vision_client = vision_client or MockVisionValidationClient()
        self.text_client = text_client or MockTextGenerationClient()
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self._jobs: Queue[AIJob] = Queue()
        self._worker = _AIJobWorker(self)

    @classmethod
    def from_config(cls, config: MoggieConfig, *, event_bus: EventBus) -> "AIJobService":
        video_client: VideoGenerationClient | None = None
        if config.enable_pika and config.fal_key:
            video_client = FalPikaClient(
                api_key=config.fal_key,
                model=config.pika_model,
                timeout_seconds=config.ai_timeout_seconds,
                poll_interval_seconds=config.ai_poll_interval_seconds,
                on_status=lambda job_id, status, metadata: event_bus.publish(
                    AppEvent.create(
                        EVENT_AI_JOB_UPDATE,
                        payload=ai_job_update_payload(job_id, status, **metadata),
                    )
                ),
            )
        return cls(event_bus=event_bus, video_client=video_client, timeout_seconds=config.ai_timeout_seconds)

    @property
    def is_running(self) -> bool:
        return self._worker.is_running

    def start(self) -> None:
        self._worker.start()

    def stop(self) -> None:
        self._worker.stop()

    def submit(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> str:
        job = AIJob(id=new_id("ai"), kind=kind, payload=payload or {}, timeout_seconds=timeout_seconds)
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

    async def _run_job(self, job: AIJob) -> dict[str, Any]:
        if self.handler is not None:
            return await asyncio.to_thread(self.handler, job.payload)

        kind = job.kind
        payload = job.payload
        prompt = str(payload.get("prompt") or self._default_prompt(job))
        image_bytes = payload.get("image_bytes") if isinstance(payload.get("image_bytes"), bytes) else b""
        metadata = {"job_id": job.id, "kind": kind, **payload}

        if "caricature" in kind or kind.endswith(".image") or kind == "image":
            return await self.image_client.generate_caricature(image_bytes, prompt, metadata)
        if "video" in kind:
            image_url = str(payload.get("image_url") or payload.get("source_uri") or "mock://source")
            return await self.video_client.generate_video(image_url, prompt, metadata)
        if "vision" in kind or "expression" in kind:
            expression = str(payload.get("expression") or payload.get("target_expression") or "smile")
            return await self.vision_client.classify_expression(image_bytes, expression)
        if "label" in kind or "text" in kind:
            return await self.text_client.generate_label(prompt, metadata)
        return {
            "provider": "mock",
            "kind": kind,
            "payload": payload,
            "message": "No concrete AI route configured; used local mock fallback.",
        }

    def _default_prompt(self, job: AIJob) -> str:
        if "caricature" in job.kind:
            return "Create a funny arcade caricature for the Moggie score reveal."
        if "video" in job.kind:
            return "Create a short celebratory arcade video for the winning player."
        if "label" in job.kind or "text" in job.kind:
            return "Write a short funny Moggie aura label."
        return "Run a mock AI enhancement for Moggie."


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
                timeout = job.timeout_seconds or self.service.timeout_seconds
                result = asyncio.run(asyncio.wait_for(self.service._run_job(job), timeout=timeout))
            except TimeoutError:
                self.service._publish(job, "timed_out", error=f"AI job exceeded {timeout:.1f}s timeout")
            except Exception as exc:
                self.service._publish(job, "failed", error=str(exc))
            else:
                self.service._publish(job, "succeeded", result=result)
            finally:
                self.service._jobs.task_done()
