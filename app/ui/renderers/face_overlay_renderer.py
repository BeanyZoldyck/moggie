from __future__ import annotations

from typing import Any, Mapping

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
        point_mapper: Any | None = None,
    ) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        for face in faces:
            bbox = face.get("bbox")
            if not isinstance(bbox, dict):
                continue
            zone = str(face.get("zone", ""))
            color = (255, 60, 160) if zone == "p1" else (0, 130, 255)            
            box = pygame.Rect(
                rect.left + int(float(bbox.get("x", 0.0)) * rect.width),
                rect.top + int(float(bbox.get("y", 0.0)) * rect.height),
                max(6, int(float(bbox.get("width", 0.0)) * rect.width)),
                max(6, int(float(bbox.get("height", 0.0)) * rect.height)),
            )
            pygame.draw.rect(surface, color, box, 3, border_radius=6)
            self._draw_face_geometry(pygame, surface, rect, face, point_mapper=point_mapper)
            label = "P1 FACE" if zone == "p1" else "P2 FACE"
            draw_text(surface, label, self.fonts.small, color, (box.left, max(rect.top, box.top - 24)))

    def _draw_face_geometry(self, pygame: Any, surface: Any, rect: Any, face: dict[str, Any], *, point_mapper: Any | None) -> None:
        landmarks = face.get("landmarks")
        if not isinstance(landmarks, dict):
            return
        points = {
            name: screen_point
            for name, point in landmarks.items()
            if isinstance(point, dict)
            for screen_point in [self._to_screen(rect, point, zone=str(face.get("zone", "")), point_mapper=point_mapper)]
            if screen_point is not None
        }
        zone = str(face.get("zone", ""))
        geometry_color = (255, 60, 160) if zone == "p1" else (0, 130, 255)
        shadow = (30, 10, 50)
        for start, end in FACE_GEOMETRY_CONNECTIONS:
            if start in points and end in points:
                pygame.draw.line(surface, shadow, points[start], points[end], 5)
                pygame.draw.line(surface, geometry_color, points[start], points[end], 2)
        for point in points.values():
            pygame.draw.circle(surface, shadow, point, 5)
            pygame.draw.circle(surface, geometry_color, point, 3)

    def _bbox_to_screen(
        self,
        pygame: Any,
        rect: Any,
        bbox: Mapping[str, Any],
        *,
        zone: str,
        point_mapper: Any | None,
    ) -> Any:
        top_left = self._to_screen(
            rect,
            {"x": float(bbox.get("x", 0.0)), "y": float(bbox.get("y", 0.0))},
            zone=zone,
            point_mapper=point_mapper,
        )
        bottom_right = self._to_screen(
            rect,
            {
                "x": float(bbox.get("x", 0.0)) + float(bbox.get("width", 0.0)),
                "y": float(bbox.get("y", 0.0)) + float(bbox.get("height", 0.0)),
            },
            zone=zone,
            point_mapper=point_mapper,
        )
        if top_left is None or bottom_right is None:
            return pygame.Rect(
                rect.left + int(float(bbox.get("x", 0.0)) * rect.width),
                rect.top + int(float(bbox.get("y", 0.0)) * rect.height),
                max(6, int(float(bbox.get("width", 0.0)) * rect.width)),
                max(6, int(float(bbox.get("height", 0.0)) * rect.height)),
            )
        left = min(top_left[0], bottom_right[0])
        top = min(top_left[1], bottom_right[1])
        return pygame.Rect(left, top, max(6, abs(bottom_right[0] - top_left[0])), max(6, abs(bottom_right[1] - top_left[1])))

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
