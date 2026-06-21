from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class PikaMCPError(RuntimeError):
    """Raised when Pika MCP video generation cannot complete."""


class PikaMCPAuthError(PikaMCPError):
    """Raised when Pika MCP OAuth token state is missing or unusable."""


@dataclass(frozen=True)
class PikaOAuthTokenState:
    access_token: str
    refresh_token: str = ""
    expires_at: float | None = None
    token_url: str = ""

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at - 60


class PikaTokenStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> PikaOAuthTokenState:
        if not self.path.exists():
            raise PikaMCPAuthError(f"Pika MCP OAuth token store is missing: {self.path}")
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise PikaMCPAuthError(f"Could not read Pika MCP token store: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise PikaMCPAuthError("Pika MCP token store is not valid JSON") from exc
        if not isinstance(raw, dict):
            raise PikaMCPAuthError("Pika MCP token store must contain a JSON object")
        access_token = str(raw.get("access_token") or "").strip()
        if not access_token:
            raise PikaMCPAuthError("Pika MCP token store does not contain access_token")
        expires_at = raw.get("expires_at")
        if expires_at is not None:
            try:
                expires_at = float(expires_at)
            except (TypeError, ValueError) as exc:
                raise PikaMCPAuthError("Pika MCP token store contains invalid expires_at") from exc
        return PikaOAuthTokenState(
            access_token=access_token,
            refresh_token=str(raw.get("refresh_token") or "").strip(),
            expires_at=expires_at,
            token_url=str(raw.get("token_url") or "").strip(),
        )

    def save(self, state: PikaOAuthTokenState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {"access_token": state.access_token}
        if state.refresh_token:
            payload["refresh_token"] = state.refresh_token
        if state.expires_at is not None:
            payload["expires_at"] = state.expires_at
        if state.token_url:
            payload["token_url"] = state.token_url
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self.path.chmod(0o600)


class PikaMCPTransport(Protocol):
    def request(self, url: str, payload: dict[str, Any], token: str, *, timeout: float) -> dict[str, Any]:
        ...

    def refresh_token(self, token_url: str, refresh_token: str, *, timeout: float) -> dict[str, Any]:
        ...


class StreamableHTTPPikaMCPTransport:
    def __init__(self) -> None:
        self.session_id: str | None = None

    def request(self, url: str, payload: dict[str, Any], token: str, *, timeout: float) -> dict[str, Any]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers=headers,
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                session_id = response.headers.get("Mcp-Session-Id")
                if session_id:
                    self.session_id = session_id
                return self._decode_response(response.read())
        except HTTPError as exc:
            message = self._error_message(exc.read()) or exc.reason or str(exc)
            raise PikaMCPError(f"Pika MCP HTTP {exc.code}: {message}") from exc
        except URLError as exc:
            raise PikaMCPError(f"Pika MCP network error: {exc.reason}") from exc

    def refresh_token(self, token_url: str, refresh_token: str, *, timeout: float) -> dict[str, Any]:
        request = Request(
            token_url,
            data=urlencode({"grant_type": "refresh_token", "refresh_token": refresh_token}).encode("utf-8"),
            method="POST",
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return self._decode_response(response.read())
        except HTTPError as exc:
            message = self._error_message(exc.read()) or exc.reason or str(exc)
            raise PikaMCPAuthError(f"Pika MCP token refresh HTTP {exc.code}: {message}") from exc
        except URLError as exc:
            raise PikaMCPAuthError(f"Pika MCP token refresh network error: {exc.reason}") from exc

    def _decode_response(self, body: bytes) -> dict[str, Any]:
        text = body.decode("utf-8", errors="replace").strip()
        if text.startswith("event:") or "\ndata:" in text:
            data_lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
            text = "\n".join(data_lines).strip()
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PikaMCPError("Pika MCP returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise PikaMCPError("Pika MCP returned a non-object JSON response")
        return decoded

    def _error_message(self, body: bytes) -> str | None:
        try:
            decoded = json.loads(body.decode("utf-8"))
        except Exception:
            return body.decode("utf-8", errors="replace").strip() or None
        if isinstance(decoded, dict):
            for key in ("error_description", "message", "error", "detail"):
                value = decoded.get(key)
                if value:
                    return str(value)
        return None


class PikaMCPClient:
    provider_name = "pika_mcp"
    kind = "video"

    def __init__(
        self,
        *,
        mcp_url: str,
        bearer_token: str = "",
        token_store: Path | PikaTokenStore | None = None,
        generation_tool: str = "",
        upload_tool: str = "",
        timeout_seconds: float = 120,
        transport: PikaMCPTransport | None = None,
    ) -> None:
        self.mcp_url = mcp_url.strip()
        self.bearer_token = bearer_token.strip()
        self.token_store = token_store if isinstance(token_store, PikaTokenStore) or token_store is None else PikaTokenStore(token_store)
        self.generation_tool = generation_tool.strip()
        self.upload_tool = upload_tool.strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.transport = transport or StreamableHTTPPikaMCPTransport()
        self.logger = logging.getLogger(__name__)
        self._initialized = False
        self._request_id = 0
        self._generation_tool_schema: dict[str, Any] = {}
        self._upload_tool_schema: dict[str, Any] = {}
        self._task_status_tool = "task_status"
        if not self.mcp_url:
            raise PikaMCPError("MOGGIE_PIKA_MCP_URL is required")

    async def generate_video(self, image_url: str, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        if not image_url or image_url == "mock://source":
            raise PikaMCPError("Pika MCP video generation requires image_url or image_bytes")
        return await self._generate_with_image_reference(image_url, prompt, metadata)

    async def generate_video_from_image(
        self,
        image_bytes: bytes,
        image_mime_type: str,
        prompt: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if not image_bytes:
            raise PikaMCPError("Pika MCP video generation requires image_bytes")
        image_url = await self._upload_image(image_bytes, image_mime_type, metadata)
        return await self._generate_with_image_reference(image_url, prompt, metadata)

    async def _upload_image(self, image_bytes: bytes, image_mime_type: str, metadata: dict[str, Any]) -> str:
        tool_name = await self._upload_tool()
        filename = str(metadata.get("filename") or metadata.get("display_name") or "moggie-replay").strip()
        if not filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            filename = f"{filename}.jpg"
        arguments = {
            "filename": filename,
            "mime_type": image_mime_type,
            "size_bytes": len(image_bytes),
            "ttl_s": 900,
        }
        response = await self._rpc("tools/call", {"name": tool_name, "arguments": arguments})
        result = response.get("result") if isinstance(response.get("result"), dict) else response
        upload_payload = self._extract_upload_payload(result)
        presigned_url = upload_payload.get("presigned_url")
        public_url = upload_payload.get("public_url")
        if not isinstance(public_url, str) or not public_url:
            raise PikaMCPError("Pika MCP upload_asset response did not include public_url")
        if upload_payload.get("already_uploaded"):
            return public_url
        if not isinstance(presigned_url, str) or not presigned_url:
            raise PikaMCPError("Pika MCP upload_asset response did not include presigned_url")
        await asyncio.to_thread(self._put_bytes, presigned_url, image_bytes, image_mime_type)
        return public_url

    async def _generate_with_image_reference(
        self,
        image_reference: str,
        prompt: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        tool_name, tool_schema = await self._generation_tool()
        arguments = self._build_generation_arguments(image_reference, prompt, metadata, tool_schema)
        response = await self._rpc("tools/call", {"name": tool_name, "arguments": arguments})
        response = await self._resolve_task_if_needed(response)
        video_url = self._extract_video_url(response)
        if not video_url:
            raise PikaMCPError("Pika MCP response did not include a video URL")
        return {
            "provider": self.provider_name,
            "kind": self.kind,
            "uri": video_url,
            "video_url": video_url,
            "prompt": prompt,
            "tool_name": tool_name,
            "metadata": self._result_metadata(metadata),
            "raw_result": response.get("result", response),
        }

    async def _upload_tool(self) -> str:
        if self.upload_tool:
            return self.upload_tool
        await self._initialize()
        response = await self._rpc("tools/list", {})
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise PikaMCPError("Pika MCP tools/list response did not include tools")
        candidates = [tool for tool in tools if isinstance(tool, dict)]
        for tool in candidates:
            name = str(tool.get("name") or "")
            if name == "upload_asset":
                self.upload_tool = name
                schema = tool.get("inputSchema") or tool.get("input_schema") or {}
                self._upload_tool_schema = schema if isinstance(schema, dict) else {}
                return self.upload_tool
        raise PikaMCPError("Pika MCP did not advertise upload_asset")

    async def _generation_tool(self) -> tuple[str, dict[str, Any]]:
        if self.generation_tool:
            return self.generation_tool, self._generation_tool_schema
        await self._initialize()
        response = await self._rpc("tools/list", {})
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise PikaMCPError("Pika MCP tools/list response did not include tools")
        candidates = [tool for tool in tools if isinstance(tool, dict)]
        ranked = sorted(candidates, key=self._tool_score, reverse=True)
        if not ranked or self._tool_score(ranked[0]) <= 0:
            raise PikaMCPError("Pika MCP did not advertise a video generation tool")
        self.generation_tool = str(ranked[0].get("name") or "").strip()
        if not self.generation_tool:
            raise PikaMCPError("Pika MCP advertised a tool without a name")
        schema = ranked[0].get("inputSchema") or ranked[0].get("input_schema") or {}
        self._generation_tool_schema = schema if isinstance(schema, dict) else {}
        return self.generation_tool, self._generation_tool_schema

    async def _initialize(self) -> None:
        if self._initialized:
            return
        await self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "moggie", "version": "0.1.0"},
            },
        )
        self._initialized = True

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        token = await asyncio.to_thread(self._valid_access_token)
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        response = await asyncio.to_thread(
            self.transport.request,
            self.mcp_url,
            payload,
            token,
            timeout=min(30.0, self.timeout_seconds),
        )
        if response.get("error"):
            raise PikaMCPError(f"Pika MCP {method} failed: {response['error']}")
        return response

    def _valid_access_token(self) -> str:
        if self.bearer_token:
            return self.bearer_token
        if self.token_store is None:
            raise PikaMCPAuthError("Pika MCP requires MOGGIE_PIKA_MCP_BEARER_TOKEN or MOGGIE_PIKA_MCP_TOKEN_STORE")
        state = self.token_store.load()
        if not state.is_expired:
            return state.access_token
        if not state.refresh_token or not state.token_url:
            raise PikaMCPAuthError("Pika MCP OAuth token is expired and cannot be refreshed")
        refreshed = self.transport.refresh_token(state.token_url, state.refresh_token, timeout=min(30.0, self.timeout_seconds))
        access_token = str(refreshed.get("access_token") or "").strip()
        if not access_token:
            raise PikaMCPAuthError("Pika MCP token refresh did not return access_token")
        expires_at = None
        expires_in = refreshed.get("expires_in")
        if expires_in is not None:
            try:
                expires_at = time.time() + float(expires_in)
            except (TypeError, ValueError):
                expires_at = None
        new_state = PikaOAuthTokenState(
            access_token=access_token,
            refresh_token=str(refreshed.get("refresh_token") or state.refresh_token).strip(),
            expires_at=expires_at,
            token_url=state.token_url,
        )
        self.token_store.save(new_state)
        return new_state.access_token

    def _build_generation_arguments(
        self,
        image_reference: str,
        prompt: str,
        metadata: dict[str, Any],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        if properties:
            return self._schema_aware_arguments(properties, image_reference, prompt, metadata)
        return {
            "prompt": prompt,
            "reference_images": [image_reference],
            "image_types": ["reference"],
            "provider": str(metadata.get("provider") or "seedance"),
            "resolution": str(metadata.get("resolution") or "720p"),
            "duration": metadata.get("duration") or 5,
            "aspect_ratio": str(metadata.get("aspect_ratio") or "auto"),
            "prompt_adherence": str(metadata.get("prompt_adherence") or "balanced"),
            "quality_mode": str(metadata.get("quality_mode") or "pro"),
            "sound": bool(metadata.get("sound", False)),
            "watermark": bool(metadata.get("watermark", False)),
        }

    def _schema_aware_arguments(
        self,
        properties: dict[str, Any],
        image_reference: str,
        prompt: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {}
        for name, raw_schema in properties.items():
            prop_schema = raw_schema if isinstance(raw_schema, dict) else {}
            lower = name.lower()
            if lower in {"prompt", "text", "description"}:
                arguments[name] = prompt
            elif lower in {"provider"}:
                arguments[name] = str(metadata.get("provider") or "seedance")
            elif lower in {"resolution"}:
                arguments[name] = str(metadata.get("resolution") or "720p")
            elif lower in {"quality_mode"}:
                arguments[name] = str(metadata.get("quality_mode") or "pro")
            elif lower in {"aspect_ratio"}:
                arguments[name] = str(metadata.get("aspect_ratio") or "auto")
            elif lower in {"prompt_adherence"}:
                arguments[name] = str(metadata.get("prompt_adherence") or "balanced")
            elif lower in {"sound", "watermark"}:
                arguments[name] = bool(metadata.get(name, False))
            elif lower in {"duration", "duration_s", "seconds"}:
                arguments[name] = metadata.get(name) or metadata.get("duration") or 5
            elif lower == "reference_images":
                arguments[name] = [image_reference]
            elif lower == "image_types":
                arguments[name] = ["reference"]
            elif "image" in lower or "reference" in lower:
                arguments[name] = self._image_argument(prop_schema, image_reference)
        if "prompt" not in {key.lower() for key in arguments}:
            arguments["prompt"] = prompt
        return arguments

    def _image_argument(self, schema: dict[str, Any], image_reference: str) -> Any:
        if schema.get("type") == "array":
            return [image_reference]
        if schema.get("type") == "object":
            return {"url": image_reference}
        return image_reference

    async def _resolve_task_if_needed(self, response: dict[str, Any]) -> dict[str, Any]:
        task_id = self._find_task_id(response)
        if not task_id:
            return response
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            status_response = await self._rpc("tools/call", {"name": self._task_status_tool, "arguments": {"task_id": task_id}})
            status_payload = status_response.get("result") if isinstance(status_response.get("result"), dict) else status_response
            status = str(status_payload.get("status") or "").lower() if isinstance(status_payload, dict) else ""
            if status == "completed":
                return status_response
            if status in {"failed", "cancelled"}:
                raise PikaMCPError(f"Pika MCP task {task_id} ended with status {status}")
            await asyncio.sleep(2)
        raise TimeoutError(f"Pika MCP task {task_id} exceeded {self.timeout_seconds:.1f}s timeout")

    def _find_task_id(self, value: Any) -> str | None:
        if isinstance(value, dict):
            task_id = value.get("task_id")
            if isinstance(task_id, str) and task_id:
                return task_id
            for nested in value.values():
                found = self._find_task_id(nested)
                if found:
                    return found
        if isinstance(value, list):
            for nested in value:
                found = self._find_task_id(nested)
                if found:
                    return found
        return None

    def _extract_upload_payload(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            if isinstance(value.get("public_url"), str):
                return value
            for nested in value.values():
                found = self._extract_upload_payload(nested)
                if found:
                    return found
        if isinstance(value, list):
            for nested in value:
                found = self._extract_upload_payload(nested)
                if found:
                    return found
        return {}

    def _put_bytes(self, url: str, body: bytes, content_type: str) -> None:
        request = Request(
            url,
            data=body,
            method="PUT",
            headers={
                "Content-Type": content_type,
                "Content-Length": str(len(body)),
                "x-content-sha256": hashlib.sha256(body).hexdigest(),
            },
        )
        try:
            with urlopen(request, timeout=min(30.0, self.timeout_seconds)) as response:
                status = getattr(response, "status", 200)
                if status >= 400:
                    raise PikaMCPError(f"Pika asset upload failed with HTTP {status}")
        except HTTPError as exc:
            raise PikaMCPError(f"Pika asset upload HTTP {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise PikaMCPError(f"Pika asset upload network error: {exc.reason}") from exc

    def _tool_score(self, tool: dict[str, Any]) -> int:
        text = json.dumps(tool, sort_keys=True).lower()
        score = 0
        for term in ("video", "generate", "reference", "pika", "replay"):
            if term in text:
                score += 2
        for term in ("prompt", "image", "inputschema", "input_schema"):
            if term in text:
                score += 1
        for term in ("delete", "list", "describe", "account", "history", "status"):
            if term in text:
                score -= 3
        return score

    def _extract_video_url(self, response: dict[str, Any]) -> str | None:
        return self._find_url(response)

    def _find_url(self, value: Any) -> str | None:
        if isinstance(value, str):
            if value.startswith(("http://", "https://")) and any(ext in value.lower() for ext in (".mp4", ".mov", ".webm")):
                return value
            return None
        if isinstance(value, dict):
            for key in ("video_url", "url", "uri", "href"):
                nested = value.get(key)
                if isinstance(nested, str):
                    found = self._find_url(nested)
                    if found:
                        return found
            for nested in value.values():
                found = self._find_url(nested)
                if found:
                    return found
        if isinstance(value, list):
            for nested in value:
                found = self._find_url(nested)
                if found:
                    return found
        return None

    def _result_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in metadata.items()
            if key not in {"image_bytes"} and isinstance(value, (str, int, float, bool, type(None), list, dict))
        }
