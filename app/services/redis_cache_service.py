from __future__ import annotations

import json
import logging
from json import JSONDecodeError
from collections.abc import Mapping, Sequence
from typing import Any

LOGGER = logging.getLogger(__name__)


class RedisCacheService:
    def __init__(self, redis_url: str, enabled: bool = True) -> None:
        self.redis_url = redis_url
        self.enabled = enabled
        self._client: Any | None = None
        self._warned_failure = False

    def connect(self) -> None:
        if not self.enabled:
            return
        try:
            import redis

            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            self._client.ping()
        except Exception as exc:  # pragma: no cover - depends on optional service
            self._handle_failure(exc)

    @property
    def available(self) -> bool:
        return self._client is not None

    def require_client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Redis client is not available")
        return self._client

    def get_json(self, key: str) -> Any | None:
        if self._client is None:
            return None
        try:
            raw = self._client.get(key)
            return json.loads(raw) if raw else None
        except JSONDecodeError as exc:
            LOGGER.warning("Invalid Redis JSON for %s; ignoring cache entry: %s", key, exc)
            return None
        except Exception as exc:  # pragma: no cover - depends on optional service
            self._handle_failure(exc)
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        if self._client is None:
            return
        try:
            self._client.setex(key, ttl_seconds, json.dumps(value))
        except Exception as exc:  # pragma: no cover - depends on optional service
            self._handle_failure(exc)

    def delete(self, key: str) -> None:
        if self._client is None:
            return
        try:
            self._client.delete(key)
        except Exception as exc:  # pragma: no cover - depends on optional service
            self._handle_failure(exc)

    def zadd(self, key: str, member: str, score: float) -> None:
        client = self.require_client()
        try:
            client.zadd(key, {member: score})
        except Exception as exc:  # pragma: no cover - depends on optional service
            self._handle_failure(exc)
            raise RuntimeError("Redis zadd failed") from exc

    def zrevrange(self, key: str, start: int, stop: int) -> list[str]:
        client = self.require_client()
        try:
            values: Sequence[str] = client.zrevrange(key, start, stop)
            return list(values)
        except Exception as exc:  # pragma: no cover - depends on optional service
            self._handle_failure(exc)
            raise RuntimeError("Redis zrevrange failed") from exc

    def zrevrank(self, key: str, member: str) -> int | None:
        client = self.require_client()
        try:
            result = client.zrevrank(key, member)
        except Exception as exc:  # pragma: no cover - depends on optional service
            self._handle_failure(exc)
            raise RuntimeError("Redis zrevrank failed") from exc
        return int(result) if result is not None else None

    def hset_many(self, key: str, values: Mapping[str, str]) -> None:
        client = self.require_client()
        try:
            client.hset(key, mapping=dict(values))
        except Exception as exc:  # pragma: no cover - depends on optional service
            self._handle_failure(exc)
            raise RuntimeError("Redis hset failed") from exc

    def hgetall(self, key: str) -> dict[str, str]:
        client = self.require_client()
        try:
            raw: Mapping[str, str] = client.hgetall(key)
            return dict(raw)
        except Exception as exc:  # pragma: no cover - depends on optional service
            self._handle_failure(exc)
            raise RuntimeError("Redis hgetall failed") from exc

    def _handle_failure(self, exc: Exception) -> None:
        if not self._warned_failure:
            LOGGER.warning("Redis unavailable; leaderboard cache disabled: %s", exc)
            self._warned_failure = True
        self._client = None
