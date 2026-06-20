from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from app.db import connect, initialize_database
from app.services.leaderboard_service import LeaderboardService


class FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.sets: list[tuple[str, Any, int]] = []
        self.deletes: list[str] = []

    def get_json(self, key: str) -> Any | None:
        return self.values.get(key)

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        self.sets.append((key, value, ttl_seconds))
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.deletes.append(key)
        self.values.pop(key, None)


class FailingCache:
    def get_json(self, key: str) -> Any | None:
        raise RuntimeError(f"get failed for {key}")

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        raise RuntimeError(f"set failed for {key}")

    def delete(self, key: str) -> None:
        raise RuntimeError(f"delete failed for {key}")


class LeaderboardServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "moggie.sqlite"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_database_init_is_idempotent(self) -> None:
        initialize_database(self.db_path)
        initialize_database(self.db_path)

        with connect(self.db_path) as connection:
            table_names = {
                row["name"]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                )
            }

        self.assertTrue({"players", "game_sessions", "scores", "media_assets"} <= table_names)

    def test_scores_are_inserted_and_queried_per_game_type(self) -> None:
        service = LeaderboardService(self.db_path)
        mirror_session = service.create_session("mog_mirror")
        sixty_seven_session = service.create_session("sixty_seven")

        service.record_score(
            session_id=mirror_session.id,
            player_display_name="Ada",
            game_type="mog_mirror",
            score=88,
            label="orbital aura",
            created_at="2026-01-01T00:00:00+00:00",
        )
        service.record_score(
            session_id=sixty_seven_session.id,
            player_display_name="Ada",
            game_type="sixty_seven",
            score=12,
            label="clean reps",
            created_at="2026-01-01T00:00:01+00:00",
        )

        mirror_scores = service.top_scores("mog_mirror")
        sixty_seven_scores = service.top_scores("sixty_seven")

        self.assertEqual(len(mirror_scores), 1)
        self.assertEqual(mirror_scores[0]["display_name"], "Ada")
        self.assertEqual(mirror_scores[0]["score"], 88)
        self.assertEqual(mirror_scores[0]["label"], "orbital aura")
        self.assertEqual(len(sixty_seven_scores), 1)
        self.assertEqual(sixty_seven_scores[0]["score"], 12)

    def test_leaderboard_orders_by_score_then_earliest_timestamp(self) -> None:
        service = LeaderboardService(self.db_path)
        session = service.create_session("mog_mirror")

        service.record_score(
            session_id=session.id,
            player_display_name="Third",
            game_type="mog_mirror",
            score=70,
            created_at="2026-01-01T00:00:00+00:00",
        )
        later_top = service.record_score(
            session_id=session.id,
            player_display_name="Second",
            game_type="mog_mirror",
            score=99,
            created_at="2026-01-01T00:00:02+00:00",
        )
        earlier_top = service.record_score(
            session_id=session.id,
            player_display_name="First",
            game_type="mog_mirror",
            score=99,
            created_at="2026-01-01T00:00:01+00:00",
        )

        entries = service.top_scores("mog_mirror")

        self.assertEqual([entry["display_name"] for entry in entries], ["First", "Second", "Third"])
        self.assertEqual(service.rank_for_score(earlier_top.id), 1)
        self.assertEqual(service.rank_for_score(later_top.id), 2)

    def test_player_rows_are_reused_by_display_name(self) -> None:
        service = LeaderboardService(self.db_path)
        first_session = service.create_session("mog_mirror")
        second_session = service.create_session("mog_mirror")

        service.record_score(
            session_id=first_session.id,
            player_display_name="Reuse Me",
            game_type="mog_mirror",
            score=50,
        )
        service.record_score(
            session_id=second_session.id,
            player_display_name="Reuse Me",
            game_type="mog_mirror",
            score=60,
        )

        with connect(self.db_path) as connection:
            player_count = connection.execute(
                "SELECT COUNT(*) AS count FROM players WHERE display_name = ?",
                ("Reuse Me",),
            ).fetchone()["count"]

        self.assertEqual(player_count, 1)

    def test_redis_cache_hit_returns_cached_leaderboard(self) -> None:
        cached = [
            {
                "display_name": "Cached",
                "score": 101,
                "label": "from redis",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ]
        cache = FakeCache()
        cache.values["leaderboard:mog_mirror:top10"] = cached
        service = LeaderboardService(self.db_path, cache=cache, cache_ttl_seconds=45)

        entries = service.top_scores("mog_mirror")

        self.assertEqual(entries, cached)
        self.assertEqual(cache.sets, [])

    def test_cache_miss_refreshes_redis_from_sqlite(self) -> None:
        cache = FakeCache()
        service = LeaderboardService(self.db_path, cache=cache, cache_ttl_seconds=45)
        session = service.create_session("emoji_face_match")
        service.record_score(
            session_id=session.id,
            player_display_name="Emoji",
            game_type="emoji_face_match",
            score=300,
            label="perfect lane",
            created_at="2026-01-01T00:00:00+00:00",
        )
        cache.sets.clear()

        entries = service.top_scores("emoji_face_match")

        self.assertEqual(entries[0]["display_name"], "Emoji")
        self.assertEqual(
            cache.sets,
            [("leaderboard:emoji_face_match:top10", entries, 45)],
        )

    def test_score_write_invalidates_affected_leaderboard_key(self) -> None:
        cache = FakeCache()
        service = LeaderboardService(self.db_path, cache=cache)
        session = service.create_session("sixty_seven")

        service.record_score(
            session_id=session.id,
            player_display_name="Repper",
            game_type="sixty_seven",
            score=67,
        )

        self.assertEqual(cache.deletes, ["leaderboard:sixty_seven:top10"])

    def test_redis_failures_fall_back_to_sqlite(self) -> None:
        service = LeaderboardService(self.db_path, cache=FailingCache())
        session = service.create_session("mog_mirror")

        service.record_score(
            session_id=session.id,
            player_display_name="Offline Cache",
            game_type="mog_mirror",
            score=77,
            created_at="2026-01-01T00:00:00+00:00",
        )
        entries = service.top_scores("mog_mirror")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["display_name"], "Offline Cache")
        self.assertEqual(entries[0]["score"], 77)

    def test_all_planned_game_types_are_supported(self) -> None:
        service = LeaderboardService(self.db_path)

        for game_type in ("mog_mirror", "sixty_seven", "emoji_face_match"):
            with self.subTest(game_type=game_type):
                session = service.create_session(game_type)
                service.record_score(
                    session_id=session.id,
                    player_display_name=f"{game_type} player",
                    game_type=game_type,
                    score=1,
                )
                self.assertEqual(service.top_scores(game_type)[0]["score"], 1)


if __name__ == "__main__":
    unittest.main()
