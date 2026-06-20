from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any, Mapping


@dataclass
class SixtySevenCounter:
    reps: int = 0
    state: str = "neutral"
    min_confidence: float = 0.55
    cooldown_ms: int = 350
    stale_after_ms: int = 500
    extend_threshold: float = 0.46
    return_threshold: float = 0.26
    min_delta: float = 0.08
    last_rep_ms: int = -1_000_000
    last_distance: float | None = None
    stale: bool = False

    def reset(self) -> None:
        self.reps = 0
        self.state = "neutral"
        self.last_rep_ms = -1_000_000
        self.last_distance = None
        self.stale = False

    def update(self, hand_distance: float, now_ms: int | None = None) -> int:
        now = 0 if now_ms is None else now_ms
        self.stale = False
        previous = self.last_distance
        self.last_distance = hand_distance
        if previous is None:
            if hand_distance >= self.extend_threshold:
                self.state = "extended"
            return self.reps

        delta = hand_distance - previous
        if self.state == "neutral" and delta > self.min_delta:
            self.state = "extended" if hand_distance >= self.extend_threshold else "extending"
        elif self.state == "extending" and hand_distance >= self.extend_threshold:
            self.state = "extended"
        elif self.state == "extended" and delta < -self.min_delta:
            self.state = "returning"
            if hand_distance <= self.return_threshold and now - self.last_rep_ms >= self.cooldown_ms:
                self.reps += 1
                self.last_rep_ms = now
                self.state = "neutral"
        elif self.state == "returning" and hand_distance <= self.return_threshold:
            if now - self.last_rep_ms >= self.cooldown_ms:
                self.reps += 1
                self.last_rep_ms = now
            self.state = "neutral"
        return self.reps

    def update_from_hands(
        self,
        hands: list[Mapping[str, Any]],
        *,
        now_ms: int,
        frame_timestamp_ms: int | None,
        require_both_hands: bool = False,
    ) -> int:
        if frame_timestamp_ms is None or now_ms - frame_timestamp_ms > self.stale_after_ms:
            self.stale = True
            return self.reps
        self.stale = False

        usable = [
            hand
            for hand in hands
            if float(hand.get("confidence", 1.0)) >= self.min_confidence
            and isinstance(hand.get("palm_center"), Mapping)
        ]
        if require_both_hands and len(usable) < 2:
            return self.reps
        if len(usable) < 2:
            return self.reps

        distance = hand_distance(usable[0], usable[1])
        return self.update(distance, now_ms=now_ms)


def hand_distance(first: Mapping[str, Any], second: Mapping[str, Any]) -> float:
    first_center = first["palm_center"]
    second_center = second["palm_center"]
    return hypot(
        float(first_center["x"]) - float(second_center["x"]),
        float(first_center["y"]) - float(second_center["y"]),
    )
