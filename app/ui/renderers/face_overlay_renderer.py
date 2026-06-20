from __future__ import annotations

from typing import Any

from app.ui import theme
from app.ui.render_utils import FontSet, build_fonts, draw_text


def _pygame() -> Any:
    import pygame

    return pygame


class FaceOverlayRenderer:
    def __init__(self) -> None:
        self.fonts: FontSet | None = None

    def render(
        self,
        surface: Any,
        rect: Any,
        faces: list[dict[str, Any]],
        *,
        split_x: float = 0.5,
    ) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        for face in faces:
            bbox = face.get("bbox")
            if not isinstance(bbox, dict):
                continue
            zone = str(face.get("zone", ""))
            color = theme.PLAYER_COLORS[0] if zone == "p1" else theme.PLAYER_COLORS[1]
            box = pygame.Rect(
                rect.left + int(float(bbox.get("x", 0.0)) * rect.width),
                rect.top + int(float(bbox.get("y", 0.0)) * rect.height),
                max(6, int(float(bbox.get("width", 0.0)) * rect.width)),
                max(6, int(float(bbox.get("height", 0.0)) * rect.height)),
            )
            pygame.draw.rect(surface, color, box, 3, border_radius=6)
            label = "P1 FACE" if zone == "p1" else "P2 FACE"
            draw_text(surface, label, self.fonts.small, color, (box.left, max(rect.top, box.top - 24)))
