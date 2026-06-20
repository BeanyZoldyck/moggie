from __future__ import annotations

from typing import Literal

PlayerZone = Literal["p1", "p2"]


def assign_zone(normalized_x: float, split_x: float = 0.5) -> PlayerZone:
    x = max(0.0, min(1.0, normalized_x))
    return "p1" if x < split_x else "p2"
