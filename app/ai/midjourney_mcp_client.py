from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class MidjourneyMCPError(RuntimeError):
    """Raised when Midjourney MCP image generation cannot complete."""


class MidjourneyAuthError(MidjourneyMCPError):
    """Raised when the local Midjourney OAuth token state is missing or unusable."""


class MCPTransport(Protocol):
    def request(self, url: str, payload: dict[str, Any], token: str, *, timeout: float) -> dict[str, Any]:
        ...

    def refresh_token(
        self,
        token_url: str,
        refresh_token: str,
        *,
        client_id: str = "",
        client_secret: str = "",
        timeout: float,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class OAuthTokenState:
    access_token: str
    refresh_token: str = ""
    expires_at: float | None = None
    token_url: str = ""

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at - 60


class MidjourneyTokenStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> OAuthTokenState:
        if not self.path.exists():
            raise MidjourneyAuthError(f"Midjourney OAuth token store is missing: {self.path}")
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise MidjourneyAuthError(f"Could not read Midjourney token store: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise MidjourneyAuthError("Midjourney token store is not valid JSON") from exc
        if not isinstance(raw, dict):
            raise MidjourneyAuthError("Midjourney token store must contain a JSON object")
        access_token = str(raw.get("access_token") or "").strip()
        if not access_token:
            raise MidjourneyAuthError("Midjourney token store does not contain access_token")
        expires_at = raw.get("expires_at")
        if expires_at is not None:
            try:
                expires_at = float(expires_at)
            except (TypeError, ValueError) as exc:
                raise MidjourneyAuthError("Midjourney token store contains invalid expires_at") from exc
        return OAuthTokenState(
            access_token=access_token,
            refresh_token=str(raw.get("refresh_token") or "").strip(),
            expires_at=expires_at,
            token_url=str(raw.get("token_url") or "").strip(),
        )

    def save(self, state: OAuthTokenState) -> None:
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


class StreamableHTTPMCPTransport:
    def __init__(self) -> None:
        self.session_id: str | None = None

    def request(self, url: str, payload: dict[str, Any], token: str, *, timeout: float) -> dict[str, Any]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
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
            if exc.code in {401, 403}:
                raise MidjourneyAuthError(f"Midjourney MCP auth failed: {message}") from exc
            raise MidjourneyMCPError(f"Midjourney MCP HTTP {exc.code}: {message}") from exc
        except URLError as exc:
            raise MidjourneyMCPError(f"Midjourney MCP network error: {exc.reason}") from exc

    def refresh_token(
        self,
        token_url: str,
        refresh_token: str,
        *,
        client_id: str = "",
        client_secret: str = "",
        timeout: float,
    ) -> dict[str, Any]:
        form = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        if client_id:
            form["client_id"] = client_id
        if client_secret:
            form["client_secret"] = client_secret
        request = Request(
            token_url,
            data=urlencode(form).encode("utf-8"),
            method="POST",
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return self._decode_response(response.read())
        except HTTPError as exc:
            message = self._error_message(exc.read()) or exc.reason or str(exc)
            raise MidjourneyAuthError(f"Midjourney token refresh HTTP {exc.code}: {message}") from exc
        except URLError as exc:
            raise MidjourneyAuthError(f"Midjourney token refresh network error: {exc.reason}") from exc

    def _decode_response(self, body: bytes) -> dict[str, Any]:
        text = body.decode("utf-8", errors="replace").strip()
        if text.startswith("event:") or "\ndata:" in text:
            data_lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
            text = "\n".join(data_lines).strip()
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MidjourneyMCPError("Midjourney MCP returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise MidjourneyMCPError("Midjourney MCP returned a non-object JSON response")
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


class MidjourneyMCPClient:
    provider_name = "midjourney"
    kind = "image"

    def __init__(
        self,
        *,
        mcp_url: str,
        token_store: Path | MidjourneyTokenStore,
        client_id: str = "",
        client_secret: str = "",
        timeout_seconds: float = 45,
        transport: MCPTransport | None = None,
    ) -> None:
        self.mcp_url = mcp_url.strip()
        self.token_store = token_store if isinstance(token_store, MidjourneyTokenStore) else MidjourneyTokenStore(token_store)
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.transport = transport or StreamableHTTPMCPTransport()
        self.logger = logging.getLogger(__name__)
        self._tool_name: str | None = None
        self._initialized = False
        self._request_id = 0
        if not self.mcp_url:
            raise MidjourneyMCPError("MOGGIE_MIDJOURNEY_MCP_URL is required")

    async def generate_caricature(self, image_bytes: bytes, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        if not image_bytes:
            raise MidjourneyMCPError("Midjourney caricature generation requires image_bytes")
        token = await asyncio.to_thread(self._valid_access_token)
        tool_name = self._tool_name or await self._discover_generation_tool(token)
        arguments = self._build_tool_arguments(image_bytes, prompt, metadata)
        response = await self._rpc(token, "tools/call", {"name": tool_name, "arguments": arguments})
        image_uri = self._extract_image_uri(response)
        if not image_uri:
            raise MidjourneyMCPError("Midjourney MCP response did not include an image URL")
        return {
            "provider": self.provider_name,
            "kind": self.kind,
            "uri": image_uri,
            "image_url": image_uri,
            "prompt": prompt,
            "tool_name": tool_name,
            "metadata": self._result_metadata(metadata),
            "raw_result": response.get("result", response),
        }

    async def _discover_generation_tool(self, token: str) -> str:
        await self._initialize(token)
        response = await self._rpc(token, "tools/list", {})
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise MidjourneyMCPError("Midjourney MCP tools/list response did not include tools")
        candidates = [tool for tool in tools if isinstance(tool, dict)]
        ranked = sorted(candidates, key=self._tool_score, reverse=True)
        if not ranked or self._tool_score(ranked[0]) <= 0:
            raise MidjourneyMCPError("Midjourney MCP did not advertise an image generation tool")
        name = str(ranked[0].get("name") or "").strip()
        if not name:
            raise MidjourneyMCPError("Midjourney MCP advertised a tool without a name")
        self._tool_name = name
        return name

    async def _initialize(self, token: str) -> None:
        if self._initialized:
            return
        await self._rpc(
            token,
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "moggie", "version": "0.1.0"},
            },
        )
        self._initialized = True

    def _valid_access_token(self) -> str:
        state = self.token_store.load()
        if not state.is_expired:
            return state.access_token
        if not state.refresh_token or not state.token_url:
            raise MidjourneyAuthError("Midjourney OAuth token is expired and cannot be refreshed")
        refreshed = self.transport.refresh_token(
            state.token_url,
            state.refresh_token,
            client_id=self.client_id,
            client_secret=self.client_secret,
            timeout=min(15.0, self.timeout_seconds),
        )
        access_token = str(refreshed.get("access_token") or "").strip()
        if not access_token:
            raise MidjourneyAuthError("Midjourney token refresh did not return access_token")
        expires_in = refreshed.get("expires_in")
        expires_at = None
        if expires_in is not None:
            try:
                expires_at = time.time() + float(expires_in)
            except (TypeError, ValueError):
                expires_at = None
        new_state = OAuthTokenState(
            access_token=access_token,
            refresh_token=str(refreshed.get("refresh_token") or state.refresh_token).strip(),
            expires_at=expires_at,
            token_url=state.token_url,
        )
        self.token_store.save(new_state)
        return new_state.access_token

    async def _rpc(self, token: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
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
            timeout=min(15.0, self.timeout_seconds),
        )
        if response.get("error"):
            raise MidjourneyMCPError(f"Midjourney MCP {method} failed: {response['error']}")
        return response

    def _build_tool_arguments(self, image_bytes: bytes, prompt: str, metadata: dict[str, Any]) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "prompt": prompt,
            "image": {
                "mime_type": str(metadata.get("image_mime_type") or "image/jpeg"),
                "data": base64.b64encode(image_bytes).decode("ascii"),
            },
            "metadata": self._result_metadata(metadata),
        }
        if metadata.get("aspect_ratio"):
            arguments["aspect_ratio"] = metadata["aspect_ratio"]
        if metadata.get("style"):
            arguments["style"] = metadata["style"]
        return arguments

    def _tool_score(self, tool: dict[str, Any]) -> int:
        text = json.dumps(tool, sort_keys=True).lower()
        score = 0
        for term in ("image", "imagine", "generate", "create"):
            if term in text:
                score += 2
        for term in ("prompt", "inputschema", "input_schema"):
            if term in text:
                score += 1
        for term in ("delete", "list", "describe", "account", "history"):
            if term in text:
                score -= 3
        return score

    def _extract_image_uri(self, response: dict[str, Any]) -> str | None:
        result = response.get("result", response)
        return self._find_uri(result)

    def _find_uri(self, value: Any) -> str | None:
        if isinstance(value, str):
            if value.startswith(("http://", "https://", "midjourney://", "data:image/")):
                return value
            return None
        if isinstance(value, dict):
            for key in ("image_url", "url", "uri", "href"):
                nested = value.get(key)
                if isinstance(nested, str):
                    found = self._find_uri(nested)
                    if found:
                        return found
            for nested in value.values():
                found = self._find_uri(nested)
                if found:
                    return found
        if isinstance(value, list):
            for nested in value:
                found = self._find_uri(nested)
                if found:
                    return found
        return None

    def _result_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in metadata.items()
            if key not in {"image_bytes"} and isinstance(value, (str, int, float, bool, type(None), list, dict))
        }
