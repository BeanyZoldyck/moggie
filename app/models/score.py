from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    id: str
    session_id: str
    player_id: str
    game_type: str
    score: int
    created_at: str
    rank: int | None = None
    label: str | None = None
    metadata_json: str | None = None
