from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

from app.config import MoggieConfig
from app.services.social_post_service import SocialPostResult, SocialPostService

LOGGER = logging.getLogger(__name__)

StatusCallback = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class VoicePostContext:
    game_type: str
    recap_url: str
    session_id: str
    winners: list[dict[str, Any]]


class VoiceAgentService:
    def __init__(
        self,
        *,
        enabled: bool,
        api_key: str,
        endpoint: str,
        social_post_service: SocialPostService,
    ) -> None:
        self.enabled = enabled and bool(api_key.strip())
        self.api_key = api_key.strip()
        self.endpoint = endpoint.strip() or "wss://agent.deepgram.com/v1/agent/converse"
        self.social_post_service = social_post_service
        self._session: _VoiceAgentSession | None = None
        self._lock = threading.Lock()

    @classmethod
    def from_config(
        cls,
        config: MoggieConfig,
        *,
        social_post_service: SocialPostService,
    ) -> "VoiceAgentService":
        return cls(
            enabled=config.enable_social_posting,
            api_key=config.deepgram_api_key,
            endpoint=config.deepgram_voice_agent_endpoint,
            social_post_service=social_post_service,
        )

    def stop(self) -> None:
        with self._lock:
            if self._session is not None:
                self._session.stop()
                self._session = None

    def begin_social_prompt(self, context: VoicePostContext, on_status: StatusCallback) -> None:
        if not self.enabled:
            on_status("disabled", {"reason": "voice-agent disabled"})
            return
        if not self.social_post_service.enabled:
            on_status("disabled", {"reason": "social posting disabled"})
            return
        with self._lock:
            if self._session is not None:
                self._session.stop()
            self._session = _VoiceAgentSession(
                api_key=self.api_key,
                endpoint=self.endpoint,
                context=context,
                social_post_service=self.social_post_service,
                on_status=on_status,
            )
            self._session.start()

    def submit_user_text(self, text: str) -> None:
        with self._lock:
            if self._session is not None:
                self._session.inject_user_text(text)


class _VoiceAgentSession:
    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        context: VoicePostContext,
        social_post_service: SocialPostService,
        on_status: StatusCallback,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.context = context
        self.social_post_service = social_post_service
        self.on_status = on_status
        self._ws: Any | None = None
        self._thread = threading.Thread(target=self._run, name="moggie-voice-agent", daemon=True)
        self._stopped = threading.Event()
        self._send_lock = threading.Lock()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        self._close_socket()

    def inject_user_text(self, text: str) -> None:
        payload = {"type": "InjectUserMessage", "content": text.strip()}
        self._send(payload)

    def _run(self) -> None:
        try:
            self._connect()
            self._send_settings()
            self.on_status(
                "prompt_started",
                {
                    "message": "Voice assistant active. Say platform, then confirm yes/no.",
                    "game_type": self.context.game_type,
                },
            )
            self._send({"type": "InjectUserMessage", "content": "Ask me which social media to post this replay on."})
            while not self._stopped.is_set():
                message = self._recv_json()
                if message is None:
                    continue
                self._handle_server_message(message)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Voice agent session failed: %s", exc)
            self.on_status("error", {"error": str(exc)})
        finally:
            self._close_socket()

    def _connect(self) -> None:
        from websocket import create_connection

        self._ws = create_connection(
            self.endpoint,
            header=[f"Authorization: Token {self.api_key}"],
            timeout=10,
        )
        self.on_status("connected", {"endpoint": self.endpoint})

    def _send_settings(self) -> None:
        settings = {
            "type": "Settings",
            "agent": {
                "language": "en",
                "think": {
                    "prompt": (
                        "You are a short arcade kiosk social posting assistant. "
                        "Ask which platform to post the replay on. Only X is supported. "
                        "If user chooses X, ask explicit confirmation before posting. "
                        "Call post_to_x only after confirmation."
                    ),
                    "functions": [
                        {
                            "name": "get_recent_recap_context",
                            "description": "Get current game recap metadata.",
                            "client_side": True,
                            "parameters": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "post_to_x",
                            "description": "Post the current recap URL to X after user confirmation.",
                            "client_side": True,
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "caption": {"type": "string"},
                                },
                            },
                        },
                        {
                            "name": "decline_post",
                            "description": "Record that the user declined to post.",
                            "client_side": True,
                            "parameters": {
                                "type": "object",
                                "properties": {"reason": {"type": "string"}},
                            },
                        },
                    ],
                },
            },
        }
        self._send(settings)

    def _handle_server_message(self, message: dict[str, Any]) -> None:
        msg_type = str(message.get("type") or "")
        if msg_type == "ConversationText":
            content = str(message.get("content") or "")
            role = str(message.get("role") or "").lower()
            if role == "assistant" and content:
                self.on_status("agent_text", {"text": content})
            return
        if msg_type == "FunctionCallRequest":
            for fn in message.get("functions", []):
                self._handle_function_call(fn)
            return
        if msg_type == "Error":
            self.on_status("error", {"error": message.get("error") or message})

    def _handle_function_call(self, fn: dict[str, Any]) -> None:
        fn_id = str(fn.get("id") or "")
        name = str(fn.get("name") or "")
        arguments_raw = str(fn.get("arguments") or "{}")
        try:
            args = json.loads(arguments_raw)
            if not isinstance(args, dict):
                args = {}
        except Exception:
            args = {}

        content: str
        if name == "get_recent_recap_context":
            content = json.dumps(
                {
                    "game_type": self.context.game_type,
                    "session_id": self.context.session_id,
                    "recap_url": self.context.recap_url,
                    "supported_platforms": ["x"],
                    "winner_names": [row.get("display_name") for row in self.context.winners if row.get("winner")],
                }
            )
        elif name == "post_to_x":
            caption = str(args.get("caption") or "").strip()
            if not caption:
                caption = self.social_post_service.compose_caption(
                    game_type=self.context.game_type,
                    recap_url=self.context.recap_url,
                    winners=self.context.winners,
                )
            result = self.social_post_service.post_to_x(recap_url=self.context.recap_url, caption=caption)
            content = json.dumps(self._result_to_dict(result))
            self.on_status("post_result", self._result_to_dict(result))
        elif name == "decline_post":
            reason = str(args.get("reason") or "user declined")
            content = json.dumps({"status": "declined", "reason": reason})
            self.on_status("declined", {"reason": reason})
        else:
            content = json.dumps({"status": "ignored", "reason": f"unknown function {name}"})

        response = {
            "type": "FunctionCallResponse",
            "id": fn_id,
            "name": name,
            "content": content,
        }
        self._send(response)

    def _result_to_dict(self, result: SocialPostResult) -> dict[str, Any]:
        return {
            "platform": result.platform,
            "status": result.status,
            "post_id": result.post_id,
            "url": result.url,
            "error": result.error,
        }

    def _recv_json(self) -> dict[str, Any] | None:
        if self._ws is None:
            return None
        try:
            raw = self._ws.recv()
        except Exception:
            return None
        if isinstance(raw, bytes):
            return None
        try:
            decoded = json.loads(raw)
        except Exception:
            return None
        if not isinstance(decoded, dict):
            return None
        return decoded

    def _send(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            return
        serialized = json.dumps(payload)
        with self._send_lock:
            self._ws.send(serialized)

    def _close_socket(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
