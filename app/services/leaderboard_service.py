from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import MoggieConfig
from app.db import connect
from app.models.player import Player
from app.models.score import Score
from app.models.session import GameSession
from app.services.redis_cache_service import RedisCacheService
from app.util.ids import new_id
from app.util.time import utc_now_iso

LOGGER = logging.getLogger(__name__)

PLANNED_GAME_TYPES = {"mog_mirror", "sixty_seven", "emoji_face_match"}
LeaderboardEntry = dict[str, Any]


class LeaderboardService:
    def __init__(
        self,
        db_path: Path,
        cache: RedisCacheService | None = None,
        cache_ttl_seconds: int = 30,
    ) -> None:
        self.db_path = db_path
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds

    @classmethod
    def from_config(cls, config: MoggieConfig) -> "LeaderboardService":
        cache = None
        if config.enable_redis_leaderboard_cache:
            cache = RedisCacheService(
                config.redis_url,
                enabled=config.enable_redis_leaderboard_cache,
            )
            cache.connect()
        return cls(
            config.db_path,
            cache=cache,
            cache_ttl_seconds=config.redis_leaderboard_ttl_seconds,
        )

    def get_or_create_player(self, display_name: str, created_at: str | None = None) -> Player:
        clean_name = self._clean_display_name(display_name)
        now = created_at or utc_now_iso()

        with connect(self.db_path) as connection:
            existing = connection.execute(
                """
                SELECT id, display_name, created_at
                FROM players
                WHERE display_name = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (clean_name,),
            ).fetchone()
            if existing is not None:
                return Player(**dict(existing))

            player = Player(
                id=new_id("player"),
                display_name=clean_name,
                created_at=now,
            )
            connection.execute(
                """
                INSERT INTO players (id, display_name, created_at)
                VALUES (?, ?, ?)
                """,
                (player.id, player.display_name, player.created_at),
            )
            connection.commit()
            return player

    def create_session(
        self,
        game_type: str,
        *,
        session_id: str | None = None,
        status: str = "running",
        started_at: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> GameSession:
        self._validate_game_type(game_type)
        session = GameSession(
            id=session_id or new_id("session"),
            game_type=game_type,
            status=status,
            started_at=started_at or utc_now_iso(),
            metadata_json=self._json_or_none(metadata),
        )

        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO game_sessions (id, game_type, status, started_at, ended_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.game_type,
                    session.status,
                    session.started_at,
                    session.ended_at,
                    session.metadata_json,
                ),
            )
            connection.commit()
        return session

    def complete_session(
        self,
        session_id: str,
        *,
        ended_at: str | None = None,
        status: str = "complete",
        metadata: Mapping[str, Any] | None = None,
    ) -> GameSession:
        finished_at = ended_at or utc_now_iso()
        metadata_json = self._json_or_none(metadata)
        with connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE game_sessions
                SET status = ?, ended_at = ?, metadata_json = COALESCE(?, metadata_json)
                WHERE id = ?
                """,
                (status, finished_at, metadata_json, session_id),
            )
            row = connection.execute(
                """
                SELECT id, game_type, status, started_at, ended_at, metadata_json
                FROM game_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            connection.commit()

        if row is None:
            raise ValueError(f"Unknown game session: {session_id}")
        return GameSession(**dict(row))

    def record_score(
        self,
        *,
        session_id: str,
        player_display_name: str,
        game_type: str,
        score: int,
        label: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        created_at: str | None = None,
    ) -> Score:
        self._validate_game_type(game_type)
        if score < 0:
            raise ValueError("score must be non-negative")

        with connect(self.db_path) as connection:
            session = connection.execute(
                """
                SELECT game_type
                FROM game_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            if session is None:
                raise ValueError(f"Unknown game session: {session_id}")
            if session["game_type"] != game_type:
                raise ValueError(
                    f"Session {session_id} is for {session['game_type']}, not {game_type}"
                )

        player = self.get_or_create_player(player_display_name)
        score_record = Score(
            id=new_id("score"),
            session_id=session_id,
            player_id=player.id,
            game_type=game_type,
            score=score,
            rank=None,
            label=label,
            metadata_json=self._json_or_none(metadata),
            created_at=created_at or utc_now_iso(),
        )

        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO scores (
                    id, session_id, player_id, game_type, score, rank, label, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score_record.id,
                    score_record.session_id,
                    score_record.player_id,
                    score_record.game_type,
                    score_record.score,
                    score_record.rank,
                    score_record.label,
                    score_record.metadata_json,
                    score_record.created_at,
                ),
            )
            connection.commit()

        if self._redis_active():
            try:
                self._index_score_in_redis(
                    score_record.id,
                    game_type,
                    score,
                    score_record.created_at,
                    player.display_name,
                    label,
                )
            except Exception as exc:
                LOGGER.warning(
                    "Redis leaderboard write failed; score persisted in SQLite only: %s",
                    exc,
                )
        rank = self.rank_for_score(score_record.id)
        with connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE scores
                SET rank = ?
                WHERE id = ?
                """,
                (rank, score_record.id),
            )
            connection.commit()
        return Score(
            id=score_record.id,
            session_id=score_record.session_id,
            player_id=score_record.player_id,
            game_type=score_record.game_type,
            score=score_record.score,
            rank=rank,
            label=score_record.label,
            metadata_json=score_record.metadata_json,
            created_at=score_record.created_at,
        )

    def top_scores(self, game_type: str, limit: int = 10) -> list[LeaderboardEntry]:
        self._validate_game_type(game_type)
        limit = max(1, min(100, limit))
        if not self._redis_active():
            return self._query_top_scores(game_type, limit)
        try:
            redis = self.cache
            assert redis is not None
            members = redis.zrevrange(self._leaderboard_key(game_type), 0, limit - 1)
            entries: list[LeaderboardEntry] = []
            for member in members:
                score_id = self._score_id_from_member(member)
                if not score_id:
                    continue
                row = redis.hgetall(self._score_hash_key(score_id))
                if not row:
                    continue
                try:
                    score_value = int(row.get("score", "0"))
                except ValueError:
                    continue
                entries.append(
                    {
                        "display_name": row.get("display_name", "Unknown"),
                        "score": score_value,
                        "label": row.get("label") or None,
                        "created_at": row.get("created_at", ""),
                    }
                )
            return entries
        except Exception as exc:
            LOGGER.warning("Redis leaderboard read failed; falling back to SQLite: %s", exc)
            return self._query_top_scores(game_type, limit)

    def record_media_asset(
        self,
        session_id: str,
        kind: str,
        uri: str,
        *,
        storage_mode: str = "remote",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist a generated media asset (video URL or local path) to the DB.

        Returns the new asset id. ``kind`` is a dotted game+type string like
        ``"mog_mirror.recap_video"``. ``storage_mode`` is ``"remote"`` for a
        fal.ai URL or ``"local"`` for a file saved to ``MOGGIE_MEDIA_DIR``.
        """
        asset_id = new_id("media")
        metadata_json = json.dumps(metadata or {})
        created_at = utc_now_iso()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO media_assets (id, session_id, player_id, kind, storage_mode, uri, metadata_json, created_at)
                VALUES (?, ?, NULL, ?, ?, ?, ?, ?)
                """,
                (asset_id, session_id, kind, storage_mode, uri, metadata_json, created_at),
            )
        LOGGER.debug("Recorded media asset %s kind=%s uri=%.80s", asset_id, kind, uri)
        return asset_id

    def recent_media_assets(self, limit: int = 6) -> list[dict[str, Any]]:
        limit = max(1, min(50, limit))
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    media_assets.kind,
                    media_assets.storage_mode,
                    media_assets.uri,
                    media_assets.created_at,
                    game_sessions.game_type,
                    players.display_name
                FROM media_assets
                LEFT JOIN game_sessions ON media_assets.session_id = game_sessions.id
                LEFT JOIN players ON media_assets.player_id = players.id
                WHERE media_assets.uri IS NOT NULL
                  AND media_assets.uri != ''
                ORDER BY media_assets.created_at DESC, media_assets.id DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in rows]

    def rank_for_score(self, score_id: str) -> int:
        if not self._redis_active():
            return self._rank_for_score_sqlite(score_id)
        try:
            redis = self.cache
            assert redis is not None
            score_row = redis.hgetall(self._score_hash_key(score_id))
            if not score_row:
                return self._rank_for_score_sqlite(score_id)
            game_type = score_row.get("game_type")
            member = score_row.get("member")
            if not game_type or not member:
                raise ValueError(f"Incomplete leaderboard metadata for score: {score_id}")
            rank = redis.zrevrank(self._leaderboard_key(game_type), member)
            if rank is None:
                return self._rank_for_score_sqlite(score_id)
            return rank + 1
        except ValueError:
            raise
        except Exception as exc:
            LOGGER.warning("Redis rank lookup failed; falling back to SQLite: %s", exc)
            return self._rank_for_score_sqlite(score_id)

    def _rank_for_score_sqlite(self, score_id: str) -> int:
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT game_type
                FROM scores
                WHERE id = ?
                """,
                (score_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown score: {score_id}")

            rows = connection.execute(
                """
                SELECT id
                FROM scores
                WHERE game_type = ?
                ORDER BY score DESC, created_at ASC, id ASC
                """,
                (row["game_type"],),
            )
            for index, score_row in enumerate(rows, start=1):
                if score_row["id"] == score_id:
                    return index

        raise ValueError(f"Unknown score: {score_id}")

    def _query_top_scores(self, game_type: str, limit: int) -> list[LeaderboardEntry]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT players.display_name, scores.score, scores.label, scores.created_at
                FROM scores
                JOIN players ON scores.player_id = players.id
                WHERE scores.game_type = ?
                ORDER BY scores.score DESC, scores.created_at ASC, scores.id ASC
                LIMIT ?
                """,
                (game_type, limit),
            )
            return [dict(row) for row in rows]

    def _redis_active(self) -> bool:
        if self.cache is None:
            return False
        if not self.cache.available:
            self.cache.connect()
        return self.cache.available

    def _leaderboard_key(self, game_type: str) -> str:
        return f"leaderboard:{game_type}:scores"

    def _score_hash_key(self, score_id: str) -> str:
        return f"leaderboard:score:{score_id}"

    def _index_score_in_redis(
        self,
        score_id: str,
        game_type: str,
        score: int,
        created_at: str,
        display_name: str,
        label: str | None,
    ) -> None:
        redis = self.cache
        if redis is None or not redis.available:
            raise RuntimeError("Redis leaderboard is unavailable.")
        member = self._member_for_score(created_at, score_id)
        redis.zadd(self._leaderboard_key(game_type), member, float(score))
        redis.hset_many(
            self._score_hash_key(score_id),
            {
                "score_id": score_id,
                "member": member,
                "game_type": game_type,
                "display_name": display_name,
                "score": str(score),
                "label": label or "",
                "created_at": created_at,
            },
        )

    def _member_for_score(self, created_at: str, score_id: str) -> str:
        # For equal scores, zrevrange breaks ties by reverse member order.
        # Inverting timestamp keeps earlier scores ahead of later ones.
        ts_ms = self._timestamp_ms(created_at)
        inverted_ts = 9_999_999_999_999 - ts_ms
        return f"{inverted_ts:013d}:{score_id}"

    def _score_id_from_member(self, member: str) -> str:
        if ":" not in member:
            return ""
        _, score_id = member.split(":", 1)
        return score_id

    def _timestamp_ms(self, created_at: str) -> int:
        normalized = created_at.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    def _get_cached_entries(self, key: str) -> list[LeaderboardEntry] | None:
        if self.cache is None:
            return None
        try:
            cached = self.cache.get_json(key)
        except Exception as exc:
            LOGGER.warning("Leaderboard cache read failed for %s: %s", key, exc)
            return None
        return cached if self._valid_entries(cached) else None

    def _set_cache(self, key: str, entries: list[LeaderboardEntry]) -> None:
        if self.cache is None:
            return
        try:
            self.cache.set_json(key, entries, self.cache_ttl_seconds)
        except Exception as exc:
            LOGGER.warning("Leaderboard cache refresh failed for %s: %s", key, exc)

    def _delete_cache(self, key: str) -> None:
        if self.cache is None:
            return
        try:
            self.cache.delete(key)
        except Exception as exc:
            LOGGER.warning("Leaderboard cache invalidation failed for %s: %s", key, exc)

    def _cache_key(self, game_type: str) -> str:
        return f"leaderboard:{game_type}:top10"

    def _validate_game_type(self, game_type: str) -> None:
        if game_type not in PLANNED_GAME_TYPES:
            expected = ", ".join(sorted(PLANNED_GAME_TYPES))
            raise ValueError(f"game_type must be one of {expected}; got {game_type!r}")

    def _clean_display_name(self, display_name: str) -> str:
        clean_name = display_name.strip()
        if not clean_name:
            raise ValueError("display_name must not be empty")
        return clean_name

    def _json_or_none(self, value: Mapping[str, Any] | None) -> str | None:
        return json.dumps(value, sort_keys=True) if value is not None else None

    def _valid_entries(self, value: Any) -> bool:
        if not isinstance(value, list):
            return False
        required_keys = {"display_name", "score", "label", "created_at"}
        return all(isinstance(entry, dict) and required_keys <= set(entry) for entry in value)
