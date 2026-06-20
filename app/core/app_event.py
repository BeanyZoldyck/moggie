from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AppEvent:
    type: str
    session_id: str | None
    timestamp_ms: int
    payload: dict[str, Any] = field(default_factory=dict)
