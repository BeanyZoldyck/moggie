from __future__ import annotations

from typing import Any, Protocol

from app.core.app_event import AppEvent
from app.models.session import GameSession


class Game(Protocol):
    game_type: str
    min_players: int
    max_players: int

    def start(self, session: GameSession) -> None:
        ...

    def handle_event(self, event: AppEvent) -> list[AppEvent]:
        ...

    def update(self, now_ms: int) -> list[AppEvent]:
        ...

    def render(self, surface: Any, state: Any) -> None:
        ...
