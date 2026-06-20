from __future__ import annotations

from app.games.base import Game


class GameRegistry:
    def __init__(self) -> None:
        self._games: dict[str, type[Game]] = {}

    def register(self, game_type: str, game_class: type[Game]) -> None:
        self._games[game_type] = game_class

    def get(self, game_type: str) -> type[Game]:
        return self._games[game_type]

    def list_game_types(self) -> list[str]:
        return sorted(self._games)
