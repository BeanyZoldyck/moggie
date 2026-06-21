from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

from app.config import MoggieConfig
from app.services.social_post_service import SocialPostResult, SocialPostService
from app.services.voice_agent_audio import VoiceAgentAudioPlayer
from app.services.voice_mic_capture import VoiceMicCapture

LOGGER = logging.getLogger(__name__)

StatusCallback = Callable[[str, dict[str, Any]], None]

_AGENT_PROMPT = (
    "You are a short arcade kiosk social posting assistant. "
    "Only X (Twitter) is supported. "
    "Ask if the player wants to post their game replay to X. "
    "If they clearly decline (no, skip, nah, etc.), call decline_post. "
    "If they clearly confirm (yes, post it, go ahead, etc.), call post_to_x. "
    "When calling post_to_x, write a short caption from their style request "
    "(snappy, hype, funny, etc.) plus game/winner context from get_recent_recap_context. "
    "Always include the recap URL in the caption. "
    "Do not call post_to_x unless the user clearly wants to post."
)


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
        voice_model: str,
        mic_sample_rate: int,
        mic_input_device: str | int | None,
        social_post_service: SocialPostService,
    ) -> None:
        self.enabled = enabled and bool(api_key.strip())
        self.api_key = api_key.strip()
        self.endpoint = endpoint.strip() or "wss://agent.deepgram.com/v1/agent/converse"
        self.voice_model = voice_model.strip() or "aura-2-atlas-en"
        self.mic_sample_rate = mic_sample_rate
        self.mic_input_device = mic_input_device
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
        device = config.voice_agent_mic_input_device
        mic_device: str | int | None = None
        if device:
            try:
                mic_device = int(device)
            except ValueError:
                mic_device = device
        return cls(
            enabled=config.enable_social_posting,
            api_key=config.deepgram_api_key,
            endpoint=config.deepgram_voice_agent_endpoint,
            voice_model=config.deepgram_voice_model,
            mic_sample_rate=config.voice_agent_mic_sample_rate,
            mic_input_device=mic_device,
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
                voice_model=self.voice_model,
                mic_sample_rate=self.mic_sample_rate,
                mic_input_device=self.mic_input_device,
                context=context,
                social_post_service=self.social_post_service,
                on_status=on_status,
            )
            self._session.start()

    def set_mic_enabled(self, enabled: bool) -> None:
        with self._lock:
            if self._session is not None:
                self._session.set_mic_enabled(enabled)

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
        voice_model: str,
        mic_sample_rate: int,
        mic_input_device: str | int | None,
        context: VoicePostContext,
        social_post_service: SocialPostService,
        on_status: StatusCallback,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.voice_model = voice_model
        self.mic_sample_rate = mic_sample_rate
        self.mic_input_device = mic_input_device
        self.context = context
        self.social_post_service = social_post_service
        self.on_status = on_status
        self._ws: Any | None = None
        self._thread = threading.Thread(target=self._run, name="moggie-voice-agent", daemon=True)
        self._stopped = threading.Event()
        self._send_lock = threading.Lock()
        self._mic_enabled = False
        self._settings_applied = threading.Event()
        self._mic = VoiceMicCapture(sample_rate=mic_sample_rate, device=mic_input_device)
        self._audio = VoiceAgentAudioPlayer()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        self._mic_enabled = False
        self._mic.stop()
        self._audio.stop()
        self._close_socket()

    def set_mic_enabled(self, enabled: bool) -> None:
        self._mic_enabled = enabled
        if enabled and not self._mic.available:
            self._mic.start()
            if not self._mic.available:
                self.on_status("mic_unavailable", {"reason": "no microphone device"})
                self._mic_enabled = False
                return
        if not enabled:
            self._audio.stop()
        self.on_status("mic_state", {"enabled": self._mic_enabled})

    def inject_user_text(self, text: str) -> None:
        payload = {"type": "InjectUserMessage", "content": text.strip()}
        self._send_json(payload)

    def _run(self) -> None:
        try:
            self._connect()
            if not self._wait_for_welcome():
                raise RuntimeError("Voice agent did not send Welcome")
            self._send_settings()
            if not self._settings_applied.wait(timeout=15):
                raise RuntimeError("Voice agent did not apply settings")
            self._mic.start()
            if not self._mic.available:
                self.on_status("mic_unavailable", {"reason": "no microphone device"})
            self.on_status(
                "prompt_started",
                {
                    "message": "Voice assistant active. Press M to turn on the mic, then speak.",
                    "game_type": self.context.game_type,
                },
            )
            while not self._stopped.is_set():
                self._pump_mic()
                message = self._recv()
                if message is None:
                    continue
                if isinstance(message, bytes):
                    self._audio.append(message)
                    continue
                self._handle_server_message(message)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Voice agent session failed: %s", exc)
            self.on_status("error", {"error": str(exc)})
        finally:
            self._mic.stop()
            self._audio.stop()
            self._close_socket()

    def _connect(self) -> None:
        from websocket import create_connection

        self._ws = create_connection(
            self.endpoint,
            header=[f"Authorization: Token {self.api_key}"],
            timeout=10,
        )
        self.on_status("connected", {"endpoint": self.endpoint})

    def _wait_for_welcome(self) -> bool:
        deadline = threading.Event()
        timer = threading.Timer(10, deadline.set)
        timer.start()
        try:
            while not self._stopped.is_set() and not deadline.is_set():
                message = self._recv()
                if message is None:
                    continue
                if isinstance(message, bytes):
                    continue
                if str(message.get("type") or "") == "Welcome":
                    return True
                self._handle_server_message(message)
        finally:
            timer.cancel()
        return False

    def _send_settings(self) -> None:
        settings = {
            "type": "Settings",
            "audio": {
                "input": {
                    "encoding": "linear16",
                    "sample_rate": self.mic_sample_rate,
                },
                "output": {
                    "encoding": "mp3",
                    "sample_rate": 24000,
                    "container": "none",
                },
            },
            "agent": {
                "listen": {
                    "provider": {
                        "type": "deepgram",
                        "model": "nova-3",
                    }
                },
                "think": {
                    "provider": {
                        "type": "open_ai",
                        "model": "gpt-4o-mini",
                    },
                    "prompt": _AGENT_PROMPT,
                    "functions": [
                        {
                            "name": "get_recent_recap_context",
                            "description": "Get current game recap metadata.",
                            "parameters": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "post_to_x",
                            "description": "Post the current recap URL to X after user confirmation.",
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
                            "parameters": {
                                "type": "object",
                                "properties": {"reason": {"type": "string"}},
                            },
                        },
                    ],
                },
                "speak": {
                    "provider": {
                        "type": "deepgram",
                        "model": self.voice_model,
                    }
                },
                "greeting": (
                    "Want to share this replay on X? "
                    "Say yes to post, or no to skip. You can also ask for a snappy or hype caption."
                ),
            },
        }
        self._send_json(settings)

    def _pump_mic(self) -> None:
        if not self._mic_enabled or self._ws is None:
            return
        for chunk in self._mic.drain():
            with self._send_lock:
                self._ws.send(chunk)

    def _handle_server_message(self, message: dict[str, Any]) -> None:
        msg_type = str(message.get("type") or "")
        if msg_type == "SettingsApplied":
            self._settings_applied.set()
            return
        if msg_type == "ConversationText":
            content = str(message.get("content") or "")
            role = str(message.get("role") or "").lower()
            if content:
                self.on_status(f"{role}_text" if role else "agent_text", {"text": content, "role": role})
            return
        if msg_type == "UserStartedSpeaking":
            self._audio.stop()
            return
        if msg_type == "AgentAudioDone":
            self._audio.flush_and_play()
            return
        if msg_type == "FunctionCallRequest":
            for fn in message.get("functions", []):
                if fn.get("client_side", True):
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
        self._send_json(response)

    def _result_to_dict(self, result: SocialPostResult) -> dict[str, Any]:
        return {
            "platform": result.platform,
            "status": result.status,
            "post_id": result.post_id,
            "url": result.url,
            "error": result.error,
        }

    def _recv(self) -> dict[str, Any] | bytes | None:
        if self._ws is None:
            return None
        try:
            self._ws.settimeout(0.05)
            raw = self._ws.recv()
        except Exception:
            return None
        if isinstance(raw, bytes):
            return raw
        try:
            decoded = json.loads(raw)
        except Exception:
            return None
        if not isinstance(decoded, dict):
            return None
        return decoded

    def _send_json(self, payload: dict[str, Any]) -> None:
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
