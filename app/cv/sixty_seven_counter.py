from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import hypot
from typing import Any, Mapping


@dataclass
class SixtySevenCounter:
    reps: int = 0
    score: float = 0.0
    score_rate: float = 0.0
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
    last_motion_sample_ms: int | None = None
    last_motion_distance: float | None = None
    last_motion_alternation: float | None = None
    stale: bool = False
    motion_deadzone: float = 0.18
    score_rate_scale: float = 260.0
    max_score_rate: float = 1_050.0

    def reset(self) -> None:
        self.reps = 0
        self.score = 0.0
        self.score_rate = 0.0
        self.state = "neutral"
        self.last_rep_ms = -1_000_000
        self.last_distance = None
        self.peak_distance = None
        self.last_alternation_sign = 0
        self.last_motion_sample_ms = None
        self.last_motion_distance = None
        self.last_motion_alternation = None
        self.stale = False

    @property
    def display_score(self) -> int:
        return max(int(self.score), self.reps)

    def tick(self, dt_ms: int, *, active: bool = True) -> int:
        dt_seconds = max(0.0, min(0.25, dt_ms / 1000.0))
        if active and self.score_rate > 1.0:
            self.score += self.score_rate * dt_seconds

        decay_per_frame = 0.92 if active and not self.stale else 0.72
        frames = dt_ms / 16.667 if dt_ms > 0 else 1.0
        self.score_rate *= decay_per_frame ** max(1.0, frames)
        if self.score_rate < 8.0:
            self.score_rate = 0.0
        return self.display_score

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
        self._update_score_rate(first, second, now_ms=now_ms)
        before = self.reps
        self.update_alternation(first, second, now_ms=now_ms)
        if self.reps > before:
            self.score_rate = max(self.score_rate, 420.0)
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

    def _update_score_rate(
        self,
        first: Mapping[str, Any],
        second: Mapping[str, Any],
        *,
        now_ms: int,
    ) -> None:
        distance = hand_distance(first, second)
        left, right = hands_by_x(first, second)
        alternation = float(left["palm_center"]["y"]) - float(right["palm_center"]["y"])

        if self.last_motion_sample_ms is None:
            self.last_motion_sample_ms = now_ms
            self.last_motion_distance = distance
            self.last_motion_alternation = alternation
            return

        elapsed_seconds = max(0.016, min(0.5, (now_ms - self.last_motion_sample_ms) / 1000.0))
        previous_distance = distance if self.last_motion_distance is None else self.last_motion_distance
        previous_alternation = alternation if self.last_motion_alternation is None else self.last_motion_alternation
        distance_delta = abs(distance - previous_distance)
        alternation_delta = abs(alternation - previous_alternation)
        velocity = (distance_delta + alternation_delta * 0.75) / elapsed_seconds

        self.last_motion_sample_ms = now_ms
        self.last_motion_distance = distance
        self.last_motion_alternation = alternation

        if velocity <= self.motion_deadzone:
            self.score_rate *= 0.55
            return

        target_rate = min(self.max_score_rate, (velocity - self.motion_deadzone) * self.score_rate_scale)
        self.score_rate = max(self.score_rate * 0.65, target_rate)


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
