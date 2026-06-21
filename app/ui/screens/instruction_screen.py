from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.game_catalog import game_for_type
from app.games.emoji_face_match import SUPPORTED_EXPRESSIONS, expression_label
from app.ui import theme
from app.ui.render_utils import (
    FontSet,
    build_fonts,
    draw_bottom_rule,
    draw_panel,
    draw_text,
    draw_wrapped_text,
    scaled_asset_image,
)


def _pygame() -> Any:
    import pygame

    return pygame


@dataclass(frozen=True)
class InstructionCopy:
    summary: str
    steps: tuple[str, ...]


INSTRUCTION_COPY: dict[str, InstructionCopy] = {
    "mog_mirror": InstructionCopy(
        summary="Face the mirror, hold your pose, and let Moggie judge the aura.",
        steps=(
            "Stand in the left or right camera lane with one face in each box.",
            "Press SPACE when both faces are framed.",
            "Hold the pose until the timer ends. The highest aura score wins.",
        ),
    ),
    "sixty_seven": InstructionCopy(
        summary="Show two hands and swap high-low positions as fast as you can.",
        steps=(
            "Keep both hands visible in your lane.",
            "Start with one hand low and one hand high.",
            "Swap high and low cleanly. Each clean swap builds reps and score rate.",
        ),
    ),
    "emoji_face_match": InstructionCopy(
        summary="Match the incoming emoji right as it reaches the target gate.",
        steps=(
            "Stay in your face lane and watch the emoji track.",
            "Make the matching face when the emoji reaches the vertical gate.",
            "A hit scores 100 points. A miss breaks the streak.",
        ),
    ),
}

EMOJI_ACTIONS: tuple[tuple[str, str], ...] = (
    ("smile", "Smile big"),
    ("surprised", "Open mouth wide"),
    ("tongue_out", "Tongue out, mouth open"),
    ("neutral", "Relax your face"),
    ("look_left", "Look left"),
    ("look_right", "Look right"),
)

EMOJI_ASSETS = {
    "neutral": "neutral.png",
    "smile": "smile.png",
    "surprised": "surprised.png",
    "tongue_out": "tongue.png",
    "look_left": "left.png",
    "look_right": "right.png",
}

BACKGROUND_ASSETS = {
    "mog_mirror": "mog_mirror_bg.png",
    "sixty_seven": "sixseven_bg.PNG",
    "emoji_face_match": "emoji_bg.PNG",
}


class InstructionScreen:
    name = "instructions"

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.fonts: FontSet | None = None
        self.return_screen = "player_setup"

    def on_enter(self, return_screen: str = "player_setup", **_: Any) -> None:
        self.return_screen = return_screen

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type != pygame.KEYDOWN:
            return
        close_keys = {pygame.K_ESCAPE, pygame.K_i, pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER}
        if event.key in close_keys:
            self.manager.go_to(self.return_screen, preserve_values=True)

    def handle_app_event(self, event: Any) -> None:
        return None

    def update(self, now_ms: int, dt_ms: int) -> None:
        return None

    def render(self, surface: Any) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        fonts = self.fonts
        width, height = surface.get_size()
        game = game_for_type(self.manager.state.selected_game_type)
        copy = INSTRUCTION_COPY[game.game_type]

        bg = scaled_asset_image(pygame, BACKGROUND_ASSETS.get(game.game_type, ""), (width, height))
        if bg is not None:
            surface.blit(bg, (0, 0))
            shade = pygame.Surface((width, height), pygame.SRCALPHA)
            shade.fill((8, 8, 10, 168))
            surface.blit(shade, (0, 0))
        else:
            surface.fill(theme.BACKGROUND)

        margin = 54
        header_y = 34
        draw_text(surface, "HOW TO PLAY", fonts.small, game.accent, (margin, header_y))
        draw_text(surface, game.title.upper(), fonts.title, theme.TEXT, (margin, header_y + 28))
        draw_wrapped_text(
            surface,
            copy.summary,
            fonts.body,
            theme.TEXT_MUTED,
            pygame.Rect(margin, header_y + 94, min(680, width - margin * 2), 64),
            max_lines=2,
        )

        visual_rect = pygame.Rect(margin, 188, width - margin * 2, 276)
        if game.game_type == "mog_mirror":
            self._render_mirror_visuals(pygame, surface, visual_rect, game.accent, fonts)
        elif game.game_type == "sixty_seven":
            self._render_sixty_seven_visuals(pygame, surface, visual_rect, game.accent, fonts)
        else:
            self._render_emoji_visuals(pygame, surface, visual_rect, game.accent, fonts)

        steps_rect = pygame.Rect(margin, height - 190, width - margin * 2, 116)
        self._render_steps(pygame, surface, steps_rect, copy.steps, game.accent, fonts)

        draw_bottom_rule(pygame, surface, height - 44, width)
        draw_text(surface, "I / SPACE / ENTER RETURNS", fonts.small, theme.TEXT_MUTED, (margin, height - 32))

    def _render_steps(
        self,
        pygame: Any,
        surface: Any,
        rect: Any,
        steps: tuple[str, ...],
        accent: tuple[int, int, int],
        fonts: FontSet,
    ) -> None:
        gap = 18
        cell_w = (rect.width - gap * (len(steps) - 1)) // len(steps)
        for index, step in enumerate(steps):
            cell = pygame.Rect(rect.left + index * (cell_w + gap), rect.top, cell_w, rect.height)
            draw_panel(pygame, surface, cell, fill=(25, 22, 26), border=theme.DIM_BORDER, width=1, radius=8)
            badge = pygame.Rect(cell.left + 16, cell.top + 16, 34, 30)
            pygame.draw.rect(surface, accent, badge, border_radius=6)
            draw_text(surface, str(index + 1), fonts.small, theme.INK, badge.center, anchor="center")
            draw_wrapped_text(
                surface,
                step,
                fonts.small,
                theme.TEXT,
                pygame.Rect(cell.left + 62, cell.top + 16, cell.width - 78, cell.height - 28),
                line_gap=4,
                max_lines=3,
            )

    def _render_mirror_visuals(
        self,
        pygame: Any,
        surface: Any,
        rect: Any,
        accent: tuple[int, int, int],
        fonts: FontSet,
    ) -> None:
        lane_rect = pygame.Rect(rect.left, rect.top, rect.width // 2 - 14, rect.height)
        meter_rect = pygame.Rect(rect.centerx + 14, rect.top, rect.width // 2 - 14, rect.height)
        draw_panel(pygame, surface, lane_rect, fill=(22, 20, 28), border=theme.BORDER, width=2)
        draw_panel(pygame, surface, meter_rect, fill=(22, 20, 28), border=theme.BORDER, width=2)

        divider_x = lane_rect.centerx
        pygame.draw.line(surface, theme.WARNING, (divider_x, lane_rect.top + 18), (divider_x, lane_rect.bottom - 18), 3)
        for index, center_x in enumerate((lane_rect.left + lane_rect.width // 4, lane_rect.right - lane_rect.width // 4)):
            color = (255, 60, 160) if index == 0 else (0, 130, 255)
            face = pygame.Rect(0, 0, 110, 138)
            face.center = (center_x, lane_rect.centery + 8)
            pygame.draw.rect(surface, color, face, 4, border_radius=8)
            pygame.draw.circle(surface, color, (face.centerx - 24, face.centery - 18), 5)
            pygame.draw.circle(surface, color, (face.centerx + 24, face.centery - 18), 5)
            pygame.draw.arc(surface, color, pygame.Rect(face.centerx - 26, face.centery, 52, 34), 0, 3.14, 3)
            draw_text(surface, f"P{index + 1} FACE", fonts.small, color, (face.left, face.top - 26))
        draw_text(surface, "Frame both faces", fonts.body, theme.TEXT, (lane_rect.centerx, lane_rect.bottom - 38), anchor="center")

        draw_text(surface, "AURA SCORE", fonts.body, accent, (meter_rect.centerx, meter_rect.top + 28), anchor="center")
        for index, height in enumerate((92, 142)):
            bar = pygame.Rect(meter_rect.left + 146 + index * 150, meter_rect.bottom - 58 - height, 68, height)
            color = (255, 60, 160) if index == 0 else (0, 130, 255)
            pygame.draw.rect(surface, (40, 34, 42), bar.inflate(18, 18), border_radius=8)
            pygame.draw.rect(surface, color, bar, border_radius=6)
            draw_text(surface, f"P{index + 1}", fonts.small, theme.TEXT, (bar.centerx, meter_rect.bottom - 42), anchor="center")
        draw_text(surface, "Hold the pose until scoring ends", fonts.small, theme.TEXT_MUTED, (meter_rect.centerx, meter_rect.bottom - 28), anchor="center")

    def _render_sixty_seven_visuals(
        self,
        pygame: Any,
        surface: Any,
        rect: Any,
        accent: tuple[int, int, int],
        fonts: FontSet,
    ) -> None:
        gap = 26
        cell_w = (rect.width - gap) // 2
        left = pygame.Rect(rect.left, rect.top, cell_w, rect.height)
        right = pygame.Rect(rect.left + cell_w + gap, rect.top, cell_w, rect.height)
        self._draw_hand_swap_frame(pygame, surface, left, low_left=True, accent=accent, fonts=fonts, label="Start")
        self._draw_hand_swap_frame(pygame, surface, right, low_left=False, accent=accent, fonts=fonts, label="Swap")

    def _draw_hand_swap_frame(
        self,
        pygame: Any,
        surface: Any,
        rect: Any,
        *,
        low_left: bool,
        accent: tuple[int, int, int],
        fonts: FontSet,
        label: str,
    ) -> None:
        draw_panel(pygame, surface, rect, fill=(23, 20, 24), border=theme.BORDER, width=2)
        draw_text(surface, label.upper(), fonts.body, accent, (rect.left + 24, rect.top + 22))
        guide = pygame.Rect(rect.left + 70, rect.top + 70, rect.width - 140, rect.height - 116)
        pygame.draw.rect(surface, (32, 28, 32), guide, border_radius=8)
        pygame.draw.line(surface, theme.DIM_BORDER, (guide.left, guide.centery), (guide.right, guide.centery), 2)

        left_y = guide.bottom - 38 if low_left else guide.top + 38
        right_y = guide.top + 38 if low_left else guide.bottom - 38
        left_pos = (guide.left + guide.width // 3, left_y)
        right_pos = (guide.right - guide.width // 3, right_y)
        self._draw_hand(pygame, surface, left_pos, (0, 255, 220))
        self._draw_hand(pygame, surface, right_pos, (255, 222, 52))
        pygame.draw.line(surface, accent, left_pos, right_pos, 4)
        draw_text(surface, "one low, one high", fonts.small, theme.TEXT_MUTED, (rect.centerx, rect.bottom - 32), anchor="center")

    def _draw_hand(self, pygame: Any, surface: Any, center: tuple[int, int], color: tuple[int, int, int]) -> None:
        pygame.draw.circle(surface, (*color, 70), center, 34)
        pygame.draw.circle(surface, color, center, 22)
        for offset in (-16, -6, 6, 16):
            pygame.draw.line(surface, color, (center[0] + offset, center[1] - 14), (center[0] + offset, center[1] - 36), 5)
        pygame.draw.circle(surface, theme.TEXT, center, 5)

    def _render_emoji_visuals(
        self,
        pygame: Any,
        surface: Any,
        rect: Any,
        accent: tuple[int, int, int],
        fonts: FontSet,
    ) -> None:
        track_rect = pygame.Rect(rect.left, rect.top, rect.width, 104)
        legend_rect = pygame.Rect(rect.left, track_rect.bottom + 18, rect.width, rect.height - track_rect.height - 18)
        self._draw_emoji_track(pygame, surface, track_rect, accent, fonts)
        self._draw_emoji_legend(pygame, surface, legend_rect, accent, fonts)

    def _draw_emoji_track(
        self,
        pygame: Any,
        surface: Any,
        rect: Any,
        accent: tuple[int, int, int],
        fonts: FontSet,
    ) -> None:
        draw_panel(pygame, surface, rect, fill=(24, 21, 26), border=theme.BORDER, width=2)
        track = pygame.Rect(rect.left + 104, rect.top + 28, rect.width - 208, 48)
        pygame.draw.line(surface, theme.DIM_BORDER, (track.left, track.centery), (track.right, track.centery), 3)
        gate_x = track.left + int(track.width * 0.72)
        pygame.draw.rect(surface, accent, pygame.Rect(gate_x - 5, track.top - 16, 10, track.height + 32), border_radius=4)
        emoji = scaled_asset_image(pygame, "smile.png", (54, 54))
        if emoji is not None:
            surface.blit(emoji, emoji.get_rect(center=(track.left + int(track.width * 0.50), track.centery)))
        else:
            draw_text(surface, ":)", fonts.body, theme.TEXT, (track.left + int(track.width * 0.50), track.centery), anchor="center")
        draw_text(surface, "make the face here", fonts.small, theme.TEXT, (gate_x, rect.bottom - 30), anchor="center")

    def _draw_emoji_legend(
        self,
        pygame: Any,
        surface: Any,
        rect: Any,
        accent: tuple[int, int, int],
        fonts: FontSet,
    ) -> None:
        columns = 3
        rows = 2
        gap = 14
        cell_w = (rect.width - gap * (columns - 1)) // columns
        cell_h = (rect.height - gap * (rows - 1)) // rows
        for index, (expression, action) in enumerate(EMOJI_ACTIONS):
            col = index % columns
            row = index // columns
            cell = pygame.Rect(rect.left + col * (cell_w + gap), rect.top + row * (cell_h + gap), cell_w, cell_h)
            draw_panel(pygame, surface, cell, fill=(25, 22, 26), border=theme.DIM_BORDER, width=1, radius=8)
            image = scaled_asset_image(pygame, EMOJI_ASSETS.get(expression, ""), (46, 46))
            image_center = (cell.left + 42, cell.centery)
            if image is not None:
                surface.blit(image, image.get_rect(center=image_center))
            else:
                draw_text(surface, expression_label(expression), fonts.small, theme.TEXT, image_center, anchor="center", max_width=70)
            draw_text(surface, expression_label(expression), fonts.small, accent, (cell.left + 82, cell.top + 15), max_width=cell.width - 96)
            draw_wrapped_text(
                surface,
                action,
                fonts.small,
                theme.TEXT,
                pygame.Rect(cell.left + 82, cell.top + 40, cell.width - 96, cell.height - 46),
                line_gap=3,
                max_lines=2,
            )


def emoji_instruction_expressions() -> tuple[str, ...]:
    return tuple(expression for expression, _ in EMOJI_ACTIONS if expression in SUPPORTED_EXPRESSIONS)
