from __future__ import annotations

import json
import logging
from typing import Any

LOGGER = logging.getLogger(__name__)


class RedisCacheService:
    def __init__(self, redis_url: str, enabled: bool = True) -> None:
        self.redis_url = redis_url
        self.enabled = enabled
        self._client: Any | None = None

    def connect(self) -> None:
        if not self.enabled:
            return
        try:
            import redis

            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            self._client.ping()
        except Exception as exc:  # pragma: no cover - depends on optional service
            LOGGER.warning("Redis unavailable; leaderboard cache disabled: %s", exc)
            self._client = None

    def get_json(self, key: str) -> Any | None:
        if self._client is None:
            return None
        raw = self._client.get(key)
        return json.loads(raw) if raw else None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        if self._client is not None:
            self._client.setex(key, ttl_seconds, json.dumps(value))

    def delete(self, key: str) -> None:
        if self._client is not None:
            self._client.delete(key)
