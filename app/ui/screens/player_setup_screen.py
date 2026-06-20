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
        surface.fill(theme.BACKGROUND)

        game = game_for_type(self.manager.state.selected_game_type)
        pygame.draw.rect(surface, (31, 24, 24), pygame.Rect(0, 0, width, 118))
        pygame.draw.rect(surface, game.accent, pygame.Rect(0, 118, width, 4))
        draw_text(surface, game.title.upper(), fonts.title, theme.TEXT, (48, 30), max_width=width - 260)
        badge_rect = pygame.Rect(width - 160, 42, 102, 34)
        draw_badge(pygame, surface, badge_rect, game.badge, fonts.small, accent=game.accent)

        panel_w = min(920, width - 96)
        panel_x = (width - panel_w) // 2
        start_y = 172
        field_gap = 28
        field_h = 112
        for index, raw_value in enumerate(self.values):
            rect = pygame.Rect(panel_x, start_y + index * (field_h + field_gap), panel_w, field_h)
            selected = index == self.active_field
            border = game.accent if selected else theme.BORDER
            draw_panel(
                pygame,
                surface,
                rect,
                fill=(38, 31, 35) if selected else theme.SURFACE,
                border=border,
                width=3 if selected else 1,
            )
            zone_label = "LEFT ZONE" if index == 0 else "RIGHT ZONE"
            if len(self.values) == 1:
                zone_label = "CENTER ZONE"
            draw_text(surface, f"PLAYER {index + 1}", fonts.small, theme.TEXT_MUTED, (rect.left + 26, rect.top + 18))
            draw_text(
                surface,
                zone_label,
                fonts.small,
                game.accent if selected else theme.TEXT_MUTED,
                (rect.right - 26, rect.top + 18),
                anchor="topright",
            )
            fallback = f"Player {index + 1}"
            value = raw_value if raw_value else fallback
            color = theme.TEXT if raw_value else theme.TEXT_MUTED
            value_rect = draw_text(
                surface,
                value,
                fonts.card_title,
                color,
                (rect.left + 26, rect.top + 52),
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

        button_y = height - 132
        button_rect = pygame.Rect((width - 288) // 2, button_y, 288, 60)
        draw_button(
            pygame,
            surface,
            button_rect,
            "LOCK NAMES",
            fonts.body,
            selected=True,
            accent=game.accent,
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
