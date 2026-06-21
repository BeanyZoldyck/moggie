from __future__ import annotations

from typing import Any

from app.ui import theme
from app.ui.render_utils import FontSet, build_fonts, draw_text

FACE_GEOMETRY_CONNECTIONS = (
    ("left_eye_outer", "left_eye_inner"),
    ("right_eye_inner", "right_eye_outer"),
    ("left_eye_inner", "nose_tip"),
    ("right_eye_inner", "nose_tip"),
    ("nose_tip", "mouth_left"),
    ("nose_tip", "mouth_right"),
    ("mouth_left", "mouth_right"),
    ("left_cheek", "chin"),
    ("right_cheek", "chin"),
    ("left_cheek", "mouth_left"),
    ("right_cheek", "mouth_right"),
)


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
            self._draw_face_geometry(pygame, surface, rect, face)
            label = "P1 FACE" if zone == "p1" else "P2 FACE"
            draw_text(surface, label, self.fonts.small, color, (box.left, max(rect.top, box.top - 24)))

    def _draw_face_geometry(self, pygame: Any, surface: Any, rect: Any, face: dict[str, Any]) -> None:
        landmarks = face.get("landmarks")
        if not isinstance(landmarks, dict):
            return
        points = {
            name: (
                rect.left + int(float(point.get("x", 0.0)) * rect.width),
                rect.top + int(float(point.get("y", 0.0)) * rect.height),
            )
            for name, point in landmarks.items()
            if isinstance(point, dict)
        }
        geometry_green = (68, 255, 126)
        shadow = (8, 34, 18)
        for start, end in FACE_GEOMETRY_CONNECTIONS:
            if start in points and end in points:
                pygame.draw.line(surface, shadow, points[start], points[end], 5)
                pygame.draw.line(surface, geometry_green, points[start], points[end], 2)
        for point in points.values():
            pygame.draw.circle(surface, shadow, point, 5)
            pygame.draw.circle(surface, geometry_green, point, 3)
