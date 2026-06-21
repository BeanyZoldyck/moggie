from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any


@dataclass
class Sparkle:
    x: float
    y: float
    size: float
    speed: float
    phase: float
    alpha: int


class SparkleLayer:
    def __init__(self, pygame: Any, width: int, height: int, count: int = 120) -> None:
        self.pygame = pygame
        self.width = width
        self.height = height
        self.count = count
        self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        self.sparkles = [self._new_sparkle() for _ in range(count)]

    def _new_sparkle(self) -> Sparkle:
        return Sparkle(
            x=random.uniform(0, self.width),
            y=random.uniform(0, self.height),
            size=random.uniform(1.5, 4.0),
            speed=random.uniform(8.0, 25.0),
            phase=random.uniform(0, math.tau),
            alpha=random.randint(90, 220),
        )

    def update(self, dt_ms: int) -> None:
        dt = dt_ms / 1000.0
        for s in self.sparkles:
            s.y -= s.speed * dt
            s.phase += dt * 4.0
            if s.y < -20:
                s.y = self.height + 20
                s.x = random.uniform(0, self.width)

    def render(self, surface: Any) -> None:
        self.surface.fill((0, 0, 0, 0))

        for s in self.sparkles:
            alpha = int((math.sin(s.phase) * 0.5 + 0.5) * s.alpha)
            color = (255, 255, 255, alpha)
            x = int(s.x)
            y = int(s.y)
            size = int(s.size + math.sin(s.phase * 2.0) * 1.5)
            
            self.pygame.draw.line(self.surface, color, (x - size, y), (x + size, y), 1)
            self.pygame.draw.line(self.surface, color, (x, y - size), (x, y + size), 1)

        surface.blit(self.surface, (0, 0))