from __future__ import annotations

import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from app.ai.midjourney_mcp_client import (
    MidjourneyAuthError,
    MidjourneyMCPClient,
    MidjourneyMCPError,
)
from app.core.app_event import EVENT_AI_JOB_UPDATE
from app.core.event_bus import EventBus
from app.services.ai_job_service import AIJobService


class FakeMCPTransport:
    def __init__(
        self,
        *,
        tools: list[dict[str, Any]] | None = None,
        call_result: dict[str, Any] | None = None,
        refreshed: dict[str, Any] | None = None,
        fail_refresh: bool = False,
        timeout: bool = False,
        call_error: bool = False,
    ) -> None:
        self.tools = tools or [
            {"name": "account_status", "description": "List account status"},
            {"name": "imagine_image", "description": "Generate an image from prompt and image"},
        ]
        self.call_result = call_result or {"content": [{"type": "image", "url": "https://cdn.midjourney.test/out.png"}]}
        self.refreshed = refreshed or {"access_token": "fresh-token", "refresh_token": "next-refresh", "expires_in": 3600}
        self.fail_refresh = fail_refresh
        self.timeout = timeout
        self.call_error = call_error
        self.requests: list[dict[str, Any]] = []
        self.refreshes: list[tuple[str, str]] = []

    def request(self, url: str, payload: dict[str, Any], token: str, *, timeout: float) -> dict[str, Any]:
        if self.timeout:
            raise TimeoutError("network stalled")
        self.requests.append({"url": url, "payload": payload, "token": token, "timeout": timeout})
        if payload["method"] == "initialize":
            return {"jsonrpc": "2.0", "id": payload["id"], "result": {"capabilities": {"tools": {}}}}
        if payload["method"] == "tools/list":
            return {"jsonrpc": "2.0", "id": payload["id"], "result": {"tools": self.tools}}
        if payload["method"] == "tools/call":
            if self.call_error:
                return {"jsonrpc": "2.0", "id": payload["id"], "error": {"message": "generation failed"}}
            return {"jsonrpc": "2.0", "id": payload["id"], "result": self.call_result}
        raise AssertionError(payload["method"])

    def refresh_token(
        self,
        token_url: str,
        refresh_token: str,
        *,
        client_id: str = "",
        client_secret: str = "",
        timeout: float,
    ) -> dict[str, Any]:
        self.refreshes.append((token_url, refresh_token))
        if self.fail_refresh:
            raise MidjourneyAuthError("refresh failed")
        return self.refreshed


class MidjourneyMCPClientTests(unittest.TestCase):
    def test_generate_caricature_discovers_tool_and_returns_image_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_path = _write_token(Path(tmp), {"access_token": "token"})
            transport = FakeMCPTransport()
            client = MidjourneyMCPClient(
                mcp_url="https://mcp.midjourney.test/mcp",
                token_store=token_path,
                transport=transport,
                timeout_seconds=10,
            )

            result = asyncio.run(client.generate_caricature(b"jpeg-bytes", "make it arcade", {"display_name": "Mina"}))

        self.assertEqual(result["provider"], "midjourney")
        self.assertEqual(result["image_url"], "https://cdn.midjourney.test/out.png")
        self.assertEqual(result["tool_name"], "imagine_image")
        self.assertEqual([request["payload"]["method"] for request in transport.requests], ["initialize", "tools/list", "tools/call"])
        call_args = transport.requests[2]["payload"]["params"]["arguments"]
        self.assertEqual(call_args["prompt"], "make it arcade")
        self.assertEqual(call_args["image"]["mime_type"], "image/jpeg")
        self.assertNotIn("image_bytes", call_args["metadata"])

    def test_missing_token_store_raises_auth_error_before_discovery(self) -> None:
        transport = FakeMCPTransport()
        client = MidjourneyMCPClient(
            mcp_url="https://mcp.midjourney.test/mcp",
            token_store=Path("/tmp/does-not-exist-midjourney-token.json"),
            transport=transport,
        )

        with self.assertRaises(MidjourneyAuthError):
            asyncio.run(client.generate_caricature(b"jpeg-bytes", "prompt", {}))

        self.assertEqual(transport.requests, [])

    def test_expired_token_refreshes_and_persists_new_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_path = _write_token(
                Path(tmp),
                {
                    "access_token": "expired-token",
                    "refresh_token": "refresh-me",
                    "expires_at": time.time() - 10,
                    "token_url": "https://auth.midjourney.test/token",
                },
            )
            transport = FakeMCPTransport()
            client = MidjourneyMCPClient(
                mcp_url="https://mcp.midjourney.test/mcp",
                token_store=token_path,
                transport=transport,
            )

            asyncio.run(client.generate_caricature(b"jpeg-bytes", "prompt", {}))
            saved = json.loads(token_path.read_text(encoding="utf-8"))
            mode = token_path.stat().st_mode & 0o777

        self.assertEqual(transport.refreshes, [("https://auth.midjourney.test/token", "refresh-me")])
        self.assertEqual(transport.requests[0]["token"], "fresh-token")
        self.assertEqual(saved["access_token"], "fresh-token")
        self.assertEqual(mode, 0o600)

    def test_expired_token_refresh_failure_is_auth_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_path = _write_token(
                Path(tmp),
                {
                    "access_token": "expired-token",
                    "refresh_token": "refresh-me",
                    "expires_at": time.time() - 10,
                    "token_url": "https://auth.midjourney.test/token",
                },
            )
            client = MidjourneyMCPClient(
                mcp_url="https://mcp.midjourney.test/mcp",
                token_store=token_path,
                transport=FakeMCPTransport(fail_refresh=True),
            )

            with self.assertRaises(MidjourneyAuthError):
                asyncio.run(client.generate_caricature(b"jpeg-bytes", "prompt", {}))

    def test_transport_timeout_propagates_to_ai_job_timeout_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_path = _write_token(Path(tmp), {"access_token": "token"})
            client = MidjourneyMCPClient(
                mcp_url="https://mcp.midjourney.test/mcp",
                token_store=token_path,
                transport=FakeMCPTransport(timeout=True),
            )

            with self.assertRaises(TimeoutError):
                asyncio.run(client.generate_caricature(b"jpeg-bytes", "prompt", {}))

    def test_generation_error_becomes_non_blocking_ai_job_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_path = _write_token(Path(tmp), {"access_token": "token"})
            image_client = MidjourneyMCPClient(
                mcp_url="https://mcp.midjourney.test/mcp",
                token_store=token_path,
                transport=FakeMCPTransport(call_error=True),
            )
            bus = EventBus()
            service = AIJobService(event_bus=bus, image_client=image_client, timeout_seconds=2)

            service.start()
            service.submit("mog_mirror.caricature", {"image_bytes": b"jpeg-bytes", "prompt": "prompt"})
            service._jobs.join()
            service.stop()
            events = [event.payload for event in bus.drain() if event.type == EVENT_AI_JOB_UPDATE]

        self.assertEqual([event["status"] for event in events], ["queued", "running", "failed"])
        self.assertIn("generation failed", events[-1]["metadata"]["error"])

    def test_no_generation_tool_is_clear_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_path = _write_token(Path(tmp), {"access_token": "token"})
            client = MidjourneyMCPClient(
                mcp_url="https://mcp.midjourney.test/mcp",
                token_store=token_path,
                transport=FakeMCPTransport(tools=[{"name": "account_status", "description": "List account status"}]),
            )

            with self.assertRaises(MidjourneyMCPError):
                asyncio.run(client.generate_caricature(b"jpeg-bytes", "prompt", {}))


def _write_token(directory: Path, payload: dict[str, Any]) -> Path:
    path = directory / "midjourney_oauth.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return path


if __name__ == "__main__":
    unittest.main()
