from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Player:
    id: str
    display_name: str
    created_at: str
