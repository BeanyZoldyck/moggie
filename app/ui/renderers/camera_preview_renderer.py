from __future__ import annotations

from typing import Any, Mapping

from app.ui import theme
from app.ui.render_utils import FontSet, build_fonts, draw_text, draw_wrapped_text, scale_to_fit


def _pygame() -> Any:
    import pygame

    return pygame


class CameraPreviewRenderer:
    def __init__(self) -> None:
        self.fonts: FontSet | None = None
        self.preview_regions: list[dict[str, Any]] = []

    def render(
        self,
        surface: Any,
        rect: Any,
        *,
        frame_bgr: Any | None,
        diagnostic: str,
        show_divider: bool = True,
        split_pane: bool = False,
    ) -> Any | None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)

        pygame.draw.rect(surface, theme.SURFACE_DARK, rect, border_radius=8)
        pygame.draw.rect(surface, theme.BORDER, rect, 2, border_radius=8)
        inner = rect.inflate(-6, -6)
        self.preview_regions = []

        if frame_bgr is None:
            self._render_diagnostic(pygame, surface, inner, diagnostic)
            return None

        if split_pane and show_divider:
            return self._render_split(pygame, surface, inner, frame_bgr)

        preview = self._surface_from_bgr(pygame, frame_bgr)
        scaled_size = scale_to_fit(preview.get_size(), inner.size)
        preview = pygame.transform.smoothscale(preview, scaled_size)
        target = preview.get_rect(center=inner.center)
        surface.blit(preview, target)
        self.preview_regions = [
            {
                "zone": "all",
                "source": (0.0, 0.0, 1.0, 1.0),
                "source_size": frame_bgr.shape[:2][::-1],
                "crop": (0, 0, frame_bgr.shape[1], frame_bgr.shape[0]),
                "dest": target,
            }
        ]
        pygame.draw.rect(surface, theme.BORDER, target, 1)
        if show_divider:
            divider_x = target.left + target.width // 2
            pygame.draw.line(surface, theme.ACCENT, (divider_x, target.top), (divider_x, target.bottom), 3)
            self._draw_zone_label(surface, "P1", (target.left + 14, target.top + 12), theme.ACCENT)
            self._draw_zone_label(surface, "P2", (target.right - 14, target.top + 12), theme.WARNING, anchor="topright")
        return target

    def _render_split(self, pygame: Any, surface: Any, rect: Any, frame_bgr: Any) -> Any:
        gap = 6
        pane_w = (rect.width - gap) // 2
        left_rect = pygame.Rect(rect.left, rect.top, pane_w, rect.height)
        right_rect = pygame.Rect(rect.left + pane_w + gap, rect.top, rect.width - pane_w - gap, rect.height)

        frame_h, frame_w = frame_bgr.shape[:2]
        split_px = frame_w // 2
        left_crop = self._blit_crop_fill(pygame, surface, frame_bgr[:, :split_px], left_rect)
        right_crop = self._blit_crop_fill(pygame, surface, frame_bgr[:, split_px:], right_rect)
        self.preview_regions = [
            {
                "zone": "p1",
                "source": (0.0, 0.0, 0.5, 1.0),
                "source_size": (split_px, frame_h),
                "crop": left_crop,
                "dest": left_rect,
            },
            {
                "zone": "p2",
                "source": (0.5, 0.0, 1.0, 1.0),
                "source_size": (frame_w - split_px, frame_h),
                "crop": right_crop,
                "dest": right_rect,
            },
        ]

        pygame.draw.rect(surface, theme.ACCENT, left_rect, 2, border_radius=4)
        pygame.draw.rect(surface, theme.WARNING, right_rect, 2, border_radius=4)
        self._draw_zone_label(surface, "P1", (left_rect.left + 10, left_rect.top + 8), theme.ACCENT)
        self._draw_zone_label(surface, "P2", (right_rect.right - 10, right_rect.top + 8), theme.WARNING, anchor="topright")
        return pygame.Rect(rect.left, rect.top, rect.width, rect.height)

    def _blit_crop_fill(self, pygame: Any, surface: Any, frame: Any, dest: Any) -> tuple[int, int, int, int]:
        src_h, src_w = frame.shape[:2]
        if src_w == 0 or src_h == 0 or dest.width == 0 or dest.height == 0:
            return (0, 0, 0, 0)
        src_ratio = src_w / src_h
        dst_ratio = dest.width / dest.height
        if src_ratio > dst_ratio:
            crop_h = src_h
            crop_w = int(crop_h * dst_ratio)
            crop_x = (src_w - crop_w) // 2
            crop_y = 0
        else:
            crop_w = src_w
            crop_h = int(crop_w / dst_ratio)
            crop_x = 0
            crop_y = (src_h - crop_h) // 2
        cropped = frame[crop_y:crop_y + crop_h, crop_x:crop_x + crop_w]
        surface.blit(self._surface_from_bgr(pygame, cropped, size=(dest.width, dest.height)), dest)
        return (crop_x, crop_y, crop_w, crop_h)

    def point_to_screen(
        self,
        point: Mapping[str, Any],
        *,
        zone: str | None = None,
        fallback_rect: Any | None = None,
    ) -> tuple[int, int] | None:
        region = self._region_for_zone(zone)

        if region is None:
            point_x = float(point["x"])
            for candidate in self.preview_regions:
                source_left, _source_top, source_right, _source_bottom = candidate["source"]
                if source_left <= point_x <= source_right:
                    region = candidate
                    break

        if region is None:
            if fallback_rect is None:
                return None
            return (
                fallback_rect.left + int(float(point["x"]) * fallback_rect.width),
                fallback_rect.top + int(float(point["y"]) * fallback_rect.height),
            )

        source_left, source_top, source_right, source_bottom = region["source"]
        source_width, source_height = region["source_size"]
        crop_x, crop_y, crop_width, crop_height = region["crop"]
        dest = region["dest"]

        local_x = (float(point["x"]) - source_left) / max(0.0001, source_right - source_left)
        local_y = (float(point["y"]) - source_top) / max(0.0001, source_bottom - source_top)
        source_px_x = local_x * source_width
        source_px_y = local_y * source_height
        screen_x = dest.left + int((source_px_x - crop_x) * dest.width / max(1, crop_width))
        screen_y = dest.top + int((source_px_y - crop_y) * dest.height / max(1, crop_height))
        return screen_x, screen_y

    def _region_for_zone(self, zone: str | None) -> dict[str, Any] | None:
        if zone is not None:
            for region in self.preview_regions:
                if region["zone"] == zone:
                    return region

        for region in self.preview_regions:
            if region["zone"] == "all":
                return region

        return None

    def _render_diagnostic(self, pygame: Any, surface: Any, rect: Any, diagnostic: str) -> None:
        assert self.fonts is not None
        icon_rect = pygame.Rect(0, 0, 72, 72)
        icon_rect.center = (rect.centerx, rect.centery - 42)
        pygame.draw.rect(surface, (42, 34, 39), icon_rect, border_radius=8)
        pygame.draw.line(surface, theme.ERROR, icon_rect.topleft, icon_rect.bottomright, 5)
        pygame.draw.line(surface, theme.ERROR, icon_rect.topright, icon_rect.bottomleft, 5)
        draw_text(surface, "CAMERA OFFLINE", self.fonts.body, theme.ERROR, (rect.centerx, rect.centery + 24), anchor="center")
        draw_wrapped_text(
            surface,
            diagnostic,
            self.fonts.small,
            theme.TEXT_MUTED,
            pygame.Rect(rect.left + 24, rect.centery + 52, rect.width - 48, 80),
            max_lines=3,
        )

    def _draw_zone_label(
        self,
        surface: Any,
        label: str,
        position: tuple[int, int],
        color: tuple[int, int, int],
        *,
        anchor: str = "topleft",
    ) -> None:
        assert self.fonts is not None
        draw_text(surface, label, self.fonts.mono, color, position, anchor=anchor)

    def _surface_from_bgr(self, pygame: Any, frame_bgr: Any, *, size: tuple[int, int] | None = None) -> Any:
        import cv2
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if size is not None:
            rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
        height, width = rgb.shape[:2]
        return pygame.image.frombuffer(rgb.tobytes(), (width, height), "RGB").convert()
