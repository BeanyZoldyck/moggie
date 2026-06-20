from __future__ import annotations

from app.models.session import GameSession
from app.util.ids import new_id
from app.util.time import utc_now_iso


class GameSessionManager:
    def create_session(self, game_type: str) -> GameSession:
        return GameSession(
            id=new_id("session"),
            game_type=game_type,
            status="created",
            started_at=utc_now_iso(),
        )
