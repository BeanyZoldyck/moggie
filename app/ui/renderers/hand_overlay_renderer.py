from __future__ import annotations

from typing import Any, Mapping

from app.ui import theme
from app.ui.render_utils import FontSet, build_fonts, draw_text


def _pygame() -> Any:
    import pygame

    return pygame


HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
)


class HandOverlayRenderer:
    def __init__(self) -> None:
        self.fonts: FontSet | None = None

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
        green = theme.ACCENT
        dim_green = (43, 142, 73)

        divider_x = rect.left + int(rect.width * split_x)
        pygame.draw.line(surface, theme.WARNING, (divider_x, rect.top), (divider_x, rect.bottom), 3)

        for hand in hands:
            points = hand.get("landmarks", [])
            if not isinstance(points, list):
                continue
            screen_points = [
                self._to_screen(rect, point, zone=str(hand.get("zone", "")), point_mapper=point_mapper)
                for point in points
                if isinstance(point, Mapping)
            ]
            screen_points = [point for point in screen_points if point is not None]
            for start, end in HAND_CONNECTIONS:
                if start < len(screen_points) and end < len(screen_points):
                    pygame.draw.line(surface, green, screen_points[start], screen_points[end], 2)
            for point in screen_points:
                pygame.draw.circle(surface, green, point, 4)

            palm = hand.get("palm_center")
            if isinstance(palm, Mapping):
                center = self._to_screen(rect, palm, zone=str(hand.get("zone", "")), point_mapper=point_mapper)
                if center is None:
                    continue
                pygame.draw.circle(surface, theme.WARNING, center, 8, 2)
                zone = str(hand.get("zone", "")).upper()
                if zone:
                    draw_text(surface, zone, self.fonts.small, green, (center[0] + 10, center[1] - 10))

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
