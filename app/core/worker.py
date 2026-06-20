from __future__ import annotations

from threading import Event, Thread


class ManagedWorker:
    def __init__(self, *, name: str) -> None:
        self.name = name
        self._stop_event = Event()
        self._thread: Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = Thread(target=self.run, name=self.name, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if not self._thread.is_alive():
                self._thread = None

    def wait(self, seconds: float) -> bool:
        return self._stop_event.wait(seconds)

    def run(self) -> None:
        raise NotImplementedError
