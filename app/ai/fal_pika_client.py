from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


FalStatusCallback = Callable[[str, str, dict[str, Any]], None]


class FalPikaError(RuntimeError):
    """Raised when Fal/Pika cannot complete a video generation request."""


class FalPikaClient:
    provider_name = "fal"
    kind = "video"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "fal-ai/pika/v2/turbo/image-to-video",
        timeout_seconds: float = 45,
        poll_interval_seconds: float = 2,
        base_url: str = "https://queue.fal.run",
        on_status: FalStatusCallback | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip().strip("/")
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.poll_interval_seconds = max(0.1, float(poll_interval_seconds))
        self.base_url = base_url.rstrip("/")
        self.on_status = on_status
        self.logger = logging.getLogger(__name__)
        if not self.api_key:
            raise FalPikaError("FAL_KEY is required for Fal/Pika video generation")
        if not self.model:
            raise FalPikaError("MOGGIE_PIKA_MODEL is required for Fal/Pika video generation")

    async def generate_video_from_image(
        self,
        image_bytes: bytes,
        image_mime_type: str,
        prompt: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a video directly from raw image bytes.

        Fal accepts a base64 data URI wherever it accepts an ``image_url``, so we
        avoid a separate upload round-trip by inlining the captured frame. This is
        the method ``AIJobService`` prefers for "video" jobs that carry image bytes.
        """
        if not image_bytes:
            raise FalPikaError("Fal/Pika image-to-video requires image bytes")
        mime = (image_mime_type or "image/jpeg").strip() or "image/jpeg"
        encoded = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:{mime};base64,{encoded}"
        result = await self.generate_video(data_uri, prompt, metadata)
        # The data URI can be hundreds of KB; don't echo it back through events/logs.
        result["image_url"] = f"data:{mime};base64,<{len(image_bytes)} bytes>"
        return result

    async def generate_video(self, image_url: str, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        if not image_url or image_url == "mock://source":
            raise FalPikaError("Fal/Pika video generation requires an image_url")

        job_id = str(metadata.get("job_id") or "")
        arguments = self._build_arguments(image_url, prompt, metadata)
        submitted = await asyncio.to_thread(self._post_json, self._model_url(), arguments)
        request_id = str(submitted.get("request_id") or "")
        if not request_id:
            raise FalPikaError("Fal queue submit response did not include request_id")

        status_url = str(submitted.get("status_url") or self._request_url(request_id, "status"))
        response_url = str(submitted.get("response_url") or self._request_url(request_id, "response"))
        status_history: list[dict[str, Any]] = []
        kind = str(metadata.get("kind") or self.kind)
        self._emit_status(
            job_id,
            "queued",
            kind=kind,
            request_id=request_id,
            fal_status="SUBMITTED",
            queue_response=submitted,
        )

        deadline = time.monotonic() + self.timeout_seconds
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Fal/Pika request {request_id} exceeded {self.timeout_seconds:.1f}s timeout")

            status_payload = await asyncio.to_thread(self._get_json, status_url)
            fal_status = str(status_payload.get("status") or "UNKNOWN")
            response_url = str(status_payload.get("response_url") or response_url)
            status_history.append(self._compact_status(status_payload))
            self._emit_status(
                job_id,
                self._map_status(fal_status),
                kind=kind,
                request_id=request_id,
                fal_status=fal_status,
                queue_position=status_payload.get("queue_position"),
                response_url=response_url,
            )

            if fal_status == "COMPLETED":
                if status_payload.get("error"):
                    raise FalPikaError(str(status_payload["error"]))
                break
            if fal_status in {"FAILED", "ERROR", "CANCELLED"}:
                raise FalPikaError(str(status_payload.get("error") or f"Fal/Pika request ended with {fal_status}"))

            await asyncio.sleep(self.poll_interval_seconds)

        result = await asyncio.to_thread(self._request_json, response_url, method="GET")
        video_url = self._extract_video_url(result)
        if not video_url:
            raise FalPikaError("Fal/Pika response did not include a video URL")

        return {
            "provider": self.provider_name,
            "kind": self.kind,
            "uri": video_url,
            "video_url": video_url,
            "image_url": image_url,
            "prompt": prompt,
            "model": self.model,
            "request_id": request_id,
            "fal_status": "COMPLETED",
            "status_history": status_history,
            "metadata": self._result_metadata(metadata),
            "raw_result": result,
        }

    def _build_arguments(self, image_url: str, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "image_url": image_url,
            "prompt": prompt,
        }
        for key in ("negative_prompt", "resolution", "duration", "seed", "aspect_ratio"):
            value = metadata.get(key)
            if value not in (None, ""):
                arguments[key] = value
        return arguments

    def _model_url(self) -> str:
        return f"{self.base_url}/{self.model}"

    def _request_url(self, request_id: str, action: str) -> str:
        return f"{self._model_url()}/requests/{request_id}/{action}"

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json(url, method="POST", payload=payload)

    def _get_json(self, url: str) -> dict[str, Any]:
        separator = "&" if "?" in url else "?"
        return self._request_json(f"{url}{separator}logs=1", method="GET")

    def _request_json(self, url: str, *, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Key {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=min(15.0, self.timeout_seconds)) as response:
                return self._decode_json(response.read())
        except HTTPError as exc:
            error_body = exc.read()
            message = self._error_message(error_body) or exc.reason or str(exc)
            self.logger.warning("Fal/Pika HTTP error %s from %s: %s", exc.code, url, message)
            raise FalPikaError(f"Fal/Pika HTTP {exc.code}: {message}") from exc
        except URLError as exc:
            self.logger.warning("Fal/Pika network error from %s: %s", url, exc.reason)
            raise FalPikaError(f"Fal/Pika network error: {exc.reason}") from exc

    def _decode_json(self, body: bytes) -> dict[str, Any]:
        try:
            decoded = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise FalPikaError("Fal/Pika returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise FalPikaError("Fal/Pika returned a non-object JSON response")
        return decoded

    def _error_message(self, body: bytes) -> str | None:
        try:
            decoded = json.loads(body.decode("utf-8"))
        except Exception:
            return body.decode("utf-8", errors="replace").strip() or None
        if isinstance(decoded, dict):
            for key in ("detail", "message", "error"):
                value = decoded.get(key)
                if value:
                    return str(value)
        if isinstance(decoded, list):
            parts: list[str] = []
            for item in decoded:
                if isinstance(item, dict):
                    msg = item.get("msg") or item.get("message")
                    err_type = item.get("type")
                    if msg and err_type:
                        parts.append(f"{err_type}: {msg}")
                    elif msg:
                        parts.append(str(msg))
            if parts:
                return "; ".join(parts)
        return None

    def _extract_video_url(self, result: dict[str, Any]) -> str | None:
        for key in ("video", "output", "file"):
            value = result.get(key)
            if isinstance(value, dict) and isinstance(value.get("url"), str):
                return value["url"]
        for key in ("video_url", "url"):
            value = result.get(key)
            if isinstance(value, str):
                return value
        videos = result.get("videos")
        if isinstance(videos, list):
            for item in videos:
                if isinstance(item, dict) and isinstance(item.get("url"), str):
                    return item["url"]
                if isinstance(item, str):
                    return item
        return None

    def _map_status(self, fal_status: str) -> str:
        if fal_status == "IN_QUEUE":
            return "queued"
        if fal_status == "IN_PROGRESS":
            return "running"
        if fal_status == "COMPLETED":
            return "running"
        return "failed"

    def _emit_status(self, job_id: str, status: str, **metadata: Any) -> None:
        if not job_id or self.on_status is None:
            return
        self.on_status(job_id, status, {"provider": self.provider_name, "model": self.model, **metadata})

    def _compact_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        compact = {
            "status": payload.get("status"),
            "request_id": payload.get("request_id"),
            "queue_position": payload.get("queue_position"),
            "metrics": payload.get("metrics"),
            "error": payload.get("error"),
            "error_type": payload.get("error_type"),
        }
        return {key: value for key, value in compact.items() if value is not None}

    def _result_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in metadata.items()
            if key not in {"image_bytes"} and isinstance(value, (str, int, float, bool, type(None), list, dict))
        }
