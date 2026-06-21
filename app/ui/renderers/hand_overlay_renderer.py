from __future__ import annotations

from typing import Any, Mapping

from app.ui import theme
from app.ui.render_utils import FontSet, build_fonts, draw_text


def _pygame() -> Any:
    import pygame

    return pygame


class HandOverlayRenderer:
    def __init__(self) -> None:
        self.fonts: FontSet | None = None
        self._trails: dict[str, list[tuple[tuple[int, int], int]]] = {}

    def render(
        self,
        surface: Any,
        rect: Any,
        hands: list[Mapping[str, Any]],
        *,
        stale: bool = False,
        split_x: float = 0.5,
        point_mapper: Any | None = None,
    ) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        dim_green = (43, 142, 73)
        now_ms = pygame.time.get_ticks()

        divider_x = rect.left + int(rect.width * split_x)
        pygame.draw.line(surface, theme.WARNING, (divider_x, rect.top), (divider_x, rect.bottom), 3)

        active_keys: set[str] = set()
        for hand in hands:
            if str(hand.get("source", "")).startswith("simple_"):
                continue
            palm = hand.get("palm_center")
            if not isinstance(palm, Mapping):
                continue
            center = self._to_screen(rect, palm, zone=str(hand.get("zone", "")), point_mapper=point_mapper)
            if center is None:
                continue
            key = self._trail_key(hand)
            active_keys.add(key)
            trail = self._trails.setdefault(key, [])
            if not trail or _distance_sq(trail[-1][0], center) >= 9:
                trail.append((center, now_ms))
            self._trails[key] = [(point, at_ms) for point, at_ms in trail if now_ms - at_ms <= 520][-18:]

        for key in list(self._trails):
            if key not in active_keys:
                self._trails[key] = [(point, at_ms) for point, at_ms in self._trails[key] if now_ms - at_ms <= 260]
                if not self._trails[key]:
                    del self._trails[key]

        glow = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for key, trail in self._trails.items():
            color = self._trail_color(key)
            self._draw_trail(pygame, glow, trail, color, now_ms)
        surface.blit(glow, (0, 0))

        if stale:
            pygame.draw.rect(surface, (60, 32, 36), rect, 4)
            draw_text(surface, "STALE TRACKING", self.fonts.small, theme.ERROR, (rect.left + 16, rect.bottom - 34))
        elif not hands:
            draw_text(surface, "SHOW HANDS", self.fonts.small, dim_green, (rect.centerx, rect.centery), anchor="center")

    def _to_screen(
        self,
        rect: Any,
        point: Mapping[str, Any],
        *,
        zone: str | None = None,
        point_mapper: Any | None = None,
    ) -> tuple[int, int] | None:
        if point_mapper is not None:
            mapped = point_mapper(point, zone=zone, fallback_rect=rect)
            if mapped is not None:
                return mapped

        return (
            rect.left + int(float(point["x"]) * rect.width),
            rect.top + int(float(point["y"]) * rect.height),
        )

    def _trail_key(self, hand: Mapping[str, Any]) -> str:
        hand_id = str(hand.get("hand_id", "hand"))
        zone = str(hand.get("zone", ""))
        return f"{zone}:{hand_id}"

    def _trail_color(self, key: str) -> tuple[int, int, int]:
        return (0, 255, 220) if key.startswith("p1:") else (255, 222, 52)

    def _draw_trail(
        self,
        pygame: Any,
        surface: Any,
        trail: list[tuple[tuple[int, int], int]],
        color: tuple[int, int, int],
        now_ms: int,
    ) -> None:
        if not trail:
            return
        for index, (point, at_ms) in enumerate(trail):
            age = max(0, now_ms - at_ms)
            fade = max(0.0, 1.0 - age / 520.0)
            size = int(7 + 17 * fade + index * 0.25)
            alpha = int(28 + 150 * fade)
            pygame.draw.circle(surface, (*color, max(0, min(255, alpha // 3))), point, size + 12)
            pygame.draw.circle(surface, (*color, max(0, min(255, alpha))), point, size)

        if len(trail) >= 2:
            for index in range(1, len(trail)):
                start, start_ms = trail[index - 1]
                end, end_ms = trail[index]
                age = max(0, now_ms - max(start_ms, end_ms))
                fade = max(0.0, 1.0 - age / 520.0)
                width = max(3, int(12 * fade))
                alpha = int(170 * fade)
                pygame.draw.line(surface, (*color, max(0, min(255, alpha))), start, end, width)

        current = trail[-1][0]
        pygame.draw.circle(surface, (*color, 72), current, 34)
        pygame.draw.circle(surface, (*color, 150), current, 24)
        pygame.draw.circle(surface, (*color, 255), current, 15)
        pygame.draw.circle(surface, (255, 255, 245, 245), current, 6)

def _distance_sq(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
