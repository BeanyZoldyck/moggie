from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any

EVENT_SESSION_STATE = "session_state"
EVENT_CV_HAND_LANDMARKS = "cv.hand_landmarks"
EVENT_CV_FACE_LANDMARKS = "cv.face_landmarks"
EVENT_SCORE_UPDATE = "score_update"
EVENT_AI_JOB_UPDATE = "ai_job_update"
EVENT_GAME_MESSAGE = "game_message"

CORE_EVENT_TYPES = {
    EVENT_SESSION_STATE,
    EVENT_CV_HAND_LANDMARKS,
    EVENT_CV_FACE_LANDMARKS,
    EVENT_SCORE_UPDATE,
    EVENT_AI_JOB_UPDATE,
    EVENT_GAME_MESSAGE,
}


@dataclass(frozen=True)
class AppEvent:
    type: str
    session_id: str | None
    timestamp_ms: int
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        event_type: str,
        *,
        session_id: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp_ms: int | None = None,
    ) -> "AppEvent":
        return cls(
            type=event_type,
            session_id=session_id,
            timestamp_ms=timestamp_ms if timestamp_ms is not None else current_time_ms(),
            payload=payload or {},
        )


def current_time_ms() -> int:
    return int(time() * 1000)


def clamp_normalized(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalized_point(x: float, y: float) -> dict[str, float]:
    return {"x": clamp_normalized(x), "y": clamp_normalized(y)}


def hand_landmarks_payload(
    hands: list[dict[str, Any]],
    *,
    frame_id: str | None = None,
) -> dict[str, Any]:
    return {
        "frame_id": frame_id,
        "hands": hands,
    }


def face_landmarks_payload(
    faces: list[dict[str, Any]],
    *,
    frame_id: str | None = None,
) -> dict[str, Any]:
    return {
        "frame_id": frame_id,
        "faces": faces,
    }


def score_update_payload(
    player_id: str,
    score: int,
    *,
    game_type: str,
    label: str | None = None,
) -> dict[str, Any]:
    return {
        "player_id": player_id,
        "game_type": game_type,
        "score": score,
        "label": label,
    }


def session_state_payload(status: str, **metadata: Any) -> dict[str, Any]:
    return {
        "status": status,
        "metadata": metadata,
    }


def ai_job_update_payload(job_id: str, status: str, **metadata: Any) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "status": status,
        "metadata": metadata,
    }


def game_message_payload(message: str, *, level: str = "info", **metadata: Any) -> dict[str, Any]:
    return {
        "message": message,
        "level": level,
        "metadata": metadata,
    }
