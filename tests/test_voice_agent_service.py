from __future__ import annotations

import json
import unittest

from app.services.social_post_service import SocialPostResult
from app.services.voice_agent_service import VoicePostContext, _VoiceAgentSession


class _FakeWs:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, message: str) -> None:
        self.sent.append(message)

    def close(self) -> None:
        return None


class _FakeSocialService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def post_to_x(self, *, recap_url: str, caption: str | None) -> SocialPostResult:
        self.calls.append((recap_url, caption or ""))
        return SocialPostResult(platform="x", status="posted", post_id="999", url="https://x.com/i/web/status/999")

    def compose_caption(self, *, game_type: str, recap_url: str, winners: list[dict[str, object]]) -> str:
        return f"{game_type} recap {recap_url}"


class VoiceAgentServiceTests(unittest.TestCase):
    def _session(self) -> tuple[_VoiceAgentSession, _FakeSocialService]:
        updates: list[tuple[str, dict[str, object]]] = []
        social = _FakeSocialService()
        session = _VoiceAgentSession(
            api_key="dg_key",
            endpoint="wss://agent.deepgram.com/v1/agent/converse",
            context=VoicePostContext(
                game_type="mog_mirror",
                recap_url="https://cdn.example/recap.mp4",
                session_id="session_1",
                winners=[{"display_name": "Mina", "winner": True}],
            ),
            social_post_service=social,  # type: ignore[arg-type]
            on_status=lambda event, payload: updates.append((event, payload)),
        )
        session._ws = _FakeWs()  # type: ignore[attr-defined]
        return session, social

    def test_handles_get_context_function_call(self) -> None:
        session, _social = self._session()
        session._handle_function_call(  # type: ignore[attr-defined]
            {"id": "fn1", "name": "get_recent_recap_context", "arguments": "{}"}
        )
        ws = session._ws  # type: ignore[attr-defined]
        payload = json.loads(ws.sent[-1])
        self.assertEqual(payload["type"], "FunctionCallResponse")
        self.assertEqual(payload["name"], "get_recent_recap_context")
        content = json.loads(payload["content"])
        self.assertEqual(content["game_type"], "mog_mirror")

    def test_handles_post_to_x_function_call(self) -> None:
        session, social = self._session()
        session._handle_function_call(  # type: ignore[attr-defined]
            {"id": "fn2", "name": "post_to_x", "arguments": json.dumps({"caption": "Post this!"})}
        )
        self.assertEqual(len(social.calls), 1)
        ws = session._ws  # type: ignore[attr-defined]
        payload = json.loads(ws.sent[-1])
        content = json.loads(payload["content"])
        self.assertEqual(content["status"], "posted")
        self.assertEqual(content["post_id"], "999")


if __name__ == "__main__":
    unittest.main()
