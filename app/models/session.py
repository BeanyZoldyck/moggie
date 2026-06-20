from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GameSession:
    id: str
    game_type: str
    status: str
    started_at: str
    ended_at: str | None = None
    metadata_json: str | None = None
