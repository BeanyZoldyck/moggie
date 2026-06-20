from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from threading import Lock

from app.core.app_event import AppEvent


class EventBus:
    def __init__(self, *, max_events: int = 1000) -> None:
        self._queue: deque[AppEvent] = deque()
        self._lock = Lock()
        self._max_events = max(1, max_events)

    def publish(self, event: AppEvent) -> None:
        with self._lock:
            self._queue.append(event)
            self._drop_overflow_locked()

    def drain(self) -> list[AppEvent]:
        with self._lock:
            events = list(self._queue)
            self._queue.clear()
            return events

    def extend(self, events: Iterable[AppEvent]) -> None:
        with self._lock:
            self._queue.extend(events)
            self._drop_overflow_locked()

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)

    def _drop_overflow_locked(self) -> None:
        while len(self._queue) > self._max_events:
            self._queue.popleft()
