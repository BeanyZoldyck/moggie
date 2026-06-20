from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from app.core.app_event import AppEvent


class EventBus:
    def __init__(self) -> None:
        self._queue: deque[AppEvent] = deque()

    def publish(self, event: AppEvent) -> None:
        self._queue.append(event)

    def drain(self) -> list[AppEvent]:
        events = list(self._queue)
        self._queue.clear()
        return events

    def extend(self, events: Iterable[AppEvent]) -> None:
        self._queue.extend(events)
