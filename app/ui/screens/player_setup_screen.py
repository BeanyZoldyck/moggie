from __future__ import annotations

from typing import Any

from app.core.game_catalog import game_for_type, player_count_for_game
from app.ui import theme
from app.ui.input import MAX_NAME_LENGTH, is_printable_text, normalize_name
from app.ui.render_utils import (
    FontSet,
    build_fonts,
    draw_badge,
    draw_bottom_rule,
    draw_button,
    draw_panel,
    draw_text,
    scaled_asset_image
)


def _pygame() -> Any:
    import pygame

    return pygame


class PlayerSetupScreen:
    name = "player_setup"

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.fonts: FontSet | None = None
        self.active_field = 0
        self.values: list[str] = []
        self.cursor_visible = True
        self._last_cursor_flip_ms = 0

    def on_enter(self, **_: Any) -> None:
        count = player_count_for_game(self.manager.state.selected_game_type, self.manager.config)
        existing = self.manager.state.player_names[:count]
        self.values = [existing[index] if index < len(existing) else "" for index in range(count)]
        self.active_field = 0
        self.cursor_visible = True
        self._last_cursor_flip_ms = 0

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.manager.go_to("home")
            return
        if event.key in {pygame.K_TAB, pygame.K_DOWN}:
            self._move_field(1)
            return
        if event.key == pygame.K_UP:
            self._move_field(-1)
            return
        if event.key in {pygame.K_RETURN, pygame.K_KP_ENTER}:
            if self.active_field < len(self.values) - 1:
                self._move_field(1)
            else:
                self._submit()
            return
        if event.key == pygame.K_BACKSPACE:
            self.values[self.active_field] = self.values[self.active_field][:-1]
            return

        text = getattr(event, "unicode", "")
        if is_printable_text(text) and len(self.values[self.active_field]) < MAX_NAME_LENGTH:
            self.values[self.active_field] += text

    def update(self, now_ms: int, dt_ms: int) -> None:
        if now_ms - self._last_cursor_flip_ms > 430:
            self.cursor_visible = not self.cursor_visible
            self._last_cursor_flip_ms = now_ms

    def render(self, surface: Any) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        fonts = self.fonts
        width, height = surface.get_size()
        bg = scaled_asset_image(pygame, "player_name_bg.png", (width, height))
        if bg is not None:
            surface.blit(bg, (0, 0))
        else:
            surface.fill(theme.BACKGROUND)

        game = game_for_type(self.manager.state.selected_game_type)


        panel_w = min(920, width - 96)
        panel_x = (width - panel_w) // 2
        start_y = 172
        field_gap = 28
        field_h = 112
        for index, raw_value in enumerate(self.values):
            if index == 0:
                rect = pygame.Rect(
                    panel_x,
                    start_y,
                    panel_w,
                    field_h
                )
            else:
                rect = pygame.Rect(
                    panel_x,
                    start_y + field_h + field_gap + 30,
                    panel_w,
                    field_h
                )
            selected = index == self.active_field
            border = game.accent if selected else theme.BORDER
            if len(self.values) == 1:
                zone_label = "CENTER ZONE"
            fallback = f"Player {index + 1}"
            value = raw_value if raw_value else fallback
            color = theme.TEXT if raw_value else theme.TEXT_MUTED
            value_rect = draw_text(
                surface,
                value,
                fonts.card_title,
                color,
                (rect.left + 400, rect.top + 105),
                max_width=rect.width - 72,
            )
            if selected and self.cursor_visible:
                cursor_x = min(value_rect.right + 6, rect.right - 32)
                pygame.draw.line(
                    surface,
                    game.accent,
                    (cursor_x, value_rect.top + 4),
                    (cursor_x, value_rect.bottom - 4),
                    3,
                )

        draw_bottom_rule(pygame, surface, height - 44, width)
        draw_text(surface, "MOGGIE", fonts.small, theme.TEXT_MUTED, (48, height - 32))

    def _move_field(self, direction: int) -> None:
        self.active_field = (self.active_field + direction) % len(self.values)
        self.cursor_visible = True

    def _submit(self) -> None:
        names = [
            normalize_name(value, fallback=f"Player {index + 1}")
            for index, value in enumerate(self.values)
        ]
        self.manager.state.player_names = names
        self.manager.state.reveal_rows = [
            {
                "display_name": name,
                "score": None,
                "label": "READY",
            }
            for name in names
        ]
        if self.manager.state.selected_game_type == "mog_mirror":
            self.manager.go_to("mog_mirror")
            return
        if self.manager.state.selected_game_type == "sixty_seven":
            self.manager.go_to("sixty_seven")
            return
        if self.manager.state.selected_game_type == "emoji_face_match":
            self.manager.go_to("emoji_face_match")
            return
        self.manager.go_to("score_reveal")
