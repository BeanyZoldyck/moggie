from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SixtySevenCounter:
    reps: int = 0
    state: str = "neutral"

    def reset(self) -> None:
        self.reps = 0
        self.state = "neutral"

    def update(self, hand_distance: float) -> int:
        if self.state == "neutral" and hand_distance > 0.65:
            self.state = "extended"
        elif self.state == "extended" and hand_distance < 0.35:
            self.reps += 1
            self.state = "neutral"
        return self.reps
