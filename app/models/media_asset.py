from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MediaAsset:
    id: str
    session_id: str
    kind: str
    storage_mode: str
    created_at: str
    player_id: str | None = None
    uri: str | None = None
    metadata_json: str | None = None
