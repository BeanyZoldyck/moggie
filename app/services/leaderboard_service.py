from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db import connect


class LeaderboardService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def top_scores(self, game_type: str, limit: int = 10) -> list[sqlite3.Row]:
        with connect(self.db_path) as connection:
            return list(
                connection.execute(
                    """
                    SELECT players.display_name, scores.score, scores.label, scores.created_at
                    FROM scores
                    JOIN players ON scores.player_id = players.id
                    WHERE scores.game_type = ?
                    ORDER BY scores.score DESC, scores.created_at ASC
                    LIMIT ?
                    """,
                    (game_type, limit),
                )
            )
