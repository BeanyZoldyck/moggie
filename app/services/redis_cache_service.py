from __future__ import annotations

import json
import logging
import ssl
from json import JSONDecodeError
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse

LOGGER = logging.getLogger(__name__)

_REDIS_CLOUD_HOST_SUFFIXES = (".redis.io", ".redislabs.com", ".redis.cloud")


class RedisCacheService:
    def __init__(self, redis_url: str, enabled: bool = True) -> None:
        self.redis_url = redis_url.strip()
        self.enabled = enabled
        self._client: Any | None = None
        self._warned_failure = False

    def connect(self) -> None:
        if not self.enabled:
            return
        try:
            import redis
        except ModuleNotFoundError as exc:
            self._handle_failure(exc)
            return

        last_exc: Exception | None = None
        for url in self._candidate_urls(self.redis_url):
            for ssl_cert_reqs in self._ssl_modes(url):
                try:
                    kwargs: dict[str, Any] = {
                        "decode_responses": True,
                        "socket_connect_timeout": 5,
                        "socket_timeout": 5,
                    }
                    if ssl_cert_reqs is not None:
                        kwargs["ssl_cert_reqs"] = ssl_cert_reqs
                    client = redis.Redis.from_url(url, **kwargs)
                    client.ping()
                    self._client = client
                    self.redis_url = url
                    LOGGER.info("Redis connected to %s", self._safe_host(url))
                    return
                except Exception as exc:  # pragma: no cover - depends on optional service
                    last_exc = exc

        self._handle_failure(last_exc or RuntimeError("Redis connection failed"))

    @property
    def available(self) -> bool:
        return self._client is not None

    def require_client(self) -> Any:
        if self._client is None:
            self.connect()
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

    def _candidate_urls(self, redis_url: str) -> list[str]:
        parsed = urlparse(redis_url)
        host = (parsed.hostname or "").lower()
        is_cloud = any(host.endswith(suffix) for suffix in _REDIS_CLOUD_HOST_SUFFIXES)
        candidates: list[str] = []
        if is_cloud and redis_url.startswith("redis://"):
            candidates.append("rediss://" + redis_url[len("redis://") :])
        candidates.append(redis_url)
        if is_cloud and redis_url.startswith("rediss://"):
            plain_url = "redis://" + redis_url[len("rediss://") :]
            if plain_url not in candidates:
                candidates.append(plain_url)
        deduped: list[str] = []
        for url in candidates:
            if url not in deduped:
                deduped.append(url)
        return deduped

    def _ssl_modes(self, url: str) -> list[Any | None]:
        if not url.startswith("rediss://"):
            return [None]
        return [ssl.CERT_REQUIRED, ssl.CERT_NONE]

    def _safe_host(self, url: str) -> str:
        parsed = urlparse(url)
        host = parsed.hostname or "unknown-host"
        port = parsed.port
        return f"{host}:{port}" if port else host

    def _handle_failure(self, exc: Exception) -> None:
        if not self._warned_failure:
            LOGGER.warning("Redis unavailable; leaderboard will fall back to SQLite: %s", exc)
            self._warned_failure = True
        self._client = None
