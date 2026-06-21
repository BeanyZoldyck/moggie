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
    def __init__(self, pygame: Any, width: int, height: int, count: int = 90) -> None:
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
            alpha=random.randint(80, 190),
        )

    def update(self, dt_ms: int) -> None:
        dt = max(0.0, min(0.1, dt_ms / 1000.0))
        for sparkle in self.sparkles:
            sparkle.y -= sparkle.speed * dt
            sparkle.phase += dt * 4.0
            if sparkle.y < -20:
                sparkle.y = self.height + 20
                sparkle.x = random.uniform(0, self.width)

    def render(self, surface: Any) -> None:
        self.surface.fill((0, 0, 0, 0))
        for sparkle in self.sparkles:
            alpha = int((math.sin(sparkle.phase) * 0.5 + 0.5) * sparkle.alpha)
            color = (255, 255, 255, alpha)
            x = int(sparkle.x)
            y = int(sparkle.y)
            size = max(1, int(sparkle.size + math.sin(sparkle.phase * 2.0) * 1.5))
            self.pygame.draw.line(self.surface, color, (x - size, y), (x + size, y), 1)
            self.pygame.draw.line(self.surface, color, (x, y - size), (x, y + size), 1)
        surface.blit(self.surface, (0, 0))


def ensure_sparkle_layer(
    pygame: Any,
    layer: SparkleLayer | None,
    width: int,
    height: int,
    *,
    count: int = 90,
) -> SparkleLayer:
    if layer is None or layer.width != width or layer.height != height or layer.count != count:
        return SparkleLayer(pygame, width, height, count=count)
    return layer
