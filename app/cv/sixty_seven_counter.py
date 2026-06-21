from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import hypot
from typing import Any, Mapping


@dataclass
class SixtySevenCounter:
    reps: int = 0
    state: str = "neutral"
    min_confidence: float = 0.55
    cooldown_ms: int = 350
    stale_after_ms: int = 500
    extend_threshold: float = 0.34
    return_threshold: float = 0.30
    min_delta: float = 0.04
    alternation_threshold: float = 0.08
    last_rep_ms: int = -1_000_000
    last_distance: float | None = None
    peak_distance: float | None = None
    last_alternation_sign: int = 0
    stale: bool = False

    def reset(self) -> None:
        self.reps = 0
        self.state = "neutral"
        self.last_rep_ms = -1_000_000
        self.last_distance = None
        self.peak_distance = None
        self.last_alternation_sign = 0
        self.stale = False

    def update(self, hand_distance: float, now_ms: int | None = None) -> int:
        now = 0 if now_ms is None else now_ms
        self.stale = False
        self.last_distance = hand_distance

        if hand_distance >= self.extend_threshold:
            self.state = "extended"
            self.peak_distance = max(self.peak_distance or hand_distance, hand_distance)
            return self.reps

        if self.state == "extended" and hand_distance <= self.return_threshold:
            peak = self.peak_distance or hand_distance
            if peak - hand_distance >= self.min_delta and now - self.last_rep_ms >= self.cooldown_ms:
                self.reps += 1
                self.last_rep_ms = now
            self.state = "neutral"
            self.peak_distance = None

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

        first, second = max(combinations(usable, 2), key=lambda pair: hand_distance(pair[0], pair[1]))
        before = self.reps
        self.update_alternation(first, second, now_ms=now_ms)
        if self.reps > before:
            return self.reps
        return self.update(hand_distance(first, second), now_ms=now_ms)

    def update_alternation(
        self,
        first: Mapping[str, Any],
        second: Mapping[str, Any],
        *,
        now_ms: int,
    ) -> int:
        left, right = hands_by_x(first, second)
        signal = float(left["palm_center"]["y"]) - float(right["palm_center"]["y"])
        magnitude = abs(signal)
        if magnitude < self.alternation_threshold:
            return self.reps

        sign = 1 if signal > 0 else -1
        if self.last_alternation_sign == 0:
            self.last_alternation_sign = sign
            return self.reps

        if sign != self.last_alternation_sign and now_ms - self.last_rep_ms >= self.cooldown_ms:
            self.reps += 1
            self.last_rep_ms = now_ms

        self.last_alternation_sign = sign
        return self.reps


def hand_distance(first: Mapping[str, Any], second: Mapping[str, Any]) -> float:
    first_center = first["palm_center"]
    second_center = second["palm_center"]
    return hypot(
        float(first_center["x"]) - float(second_center["x"]),
        float(first_center["y"]) - float(second_center["y"]),
    )


def hands_by_x(first: Mapping[str, Any], second: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if float(first["palm_center"]["x"]) <= float(second["palm_center"]["x"]):
        return first, second
    return second, first
