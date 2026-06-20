from __future__ import annotations

from typing import Any

from app.core.game_catalog import game_for_type
from app.ui import theme
from app.ui.render_utils import (
    FontSet,
    build_fonts,
    draw_bottom_rule,
    draw_button,
    draw_panel,
    draw_text,
)


def _pygame() -> Any:
    import pygame

    return pygame


class ScoreRevealScreen:
    name = "score_reveal"

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.fonts: FontSet | None = None

    def on_enter(self, **_: Any) -> None:
        return None

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type != pygame.KEYDOWN:
            return
        if event.key in {pygame.K_ESCAPE, pygame.K_h, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE}:
            self.manager.go_to("home")
        elif event.key == pygame.K_l:
            self.manager.go_to("leaderboard")

    def update(self, now_ms: int, dt_ms: int) -> None:
        return None

    def render(self, surface: Any) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        fonts = self.fonts
        width, height = surface.get_size()
        surface.fill(theme.BACKGROUND)

        game = game_for_type(self.manager.state.selected_game_type)
        pygame.draw.rect(surface, (31, 24, 24), pygame.Rect(0, 0, width, 118))
        pygame.draw.rect(surface, game.accent, pygame.Rect(0, 118, width, 4))
        draw_text(surface, "PLAYERS LOCKED", fonts.title, theme.TEXT, (48, 30), max_width=width - 96)
        draw_text(surface, game.title, fonts.body, game.accent, (52, 92), max_width=width - 104)

        rows = self.manager.state.reveal_rows or [
            {"display_name": name, "score": None, "label": "READY"}
            for name in self.manager.state.player_names
        ]
        if not rows:
            rows = [{"display_name": "Player 1", "score": None, "label": "READY"}]

        panel_w = min(920, width - 96)
        panel_x = (width - panel_w) // 2
        row_h = 104
        start_y = 174
        for index, row in enumerate(rows):
            rect = pygame.Rect(panel_x, start_y + index * (row_h + 24), panel_w, row_h)
            color = theme.PLAYER_COLORS[index % len(theme.PLAYER_COLORS)]
            draw_panel(pygame, surface, rect, fill=theme.SURFACE, border=color, width=2)
            draw_text(
                surface,
                f"P{index + 1}",
                fonts.body,
                color,
                (rect.left + 26, rect.centery),
                anchor="midleft",
            )
            draw_text(
                surface,
                str(row["display_name"]),
                fonts.card_title,
                theme.TEXT,
                (rect.left + 86, rect.centery),
                anchor="midleft",
                max_width=rect.width - 280,
            )
            score = "--" if row.get("score") is None else str(row["score"])
            draw_text(
                surface,
                score,
                fonts.card_title,
                theme.TEXT_MUTED,
                (rect.right - 34, rect.centery),
                anchor="midright",
            )

        button_y = height - 132
        home_rect = pygame.Rect(width // 2 - 224, button_y, 196, 58)
        board_rect = pygame.Rect(width // 2 + 28, button_y, 196, 58)
        draw_button(pygame, surface, home_rect, "HOME", fonts.body, selected=True, accent=game.accent)
        draw_button(pygame, surface, board_rect, "BOARD", fonts.body, selected=False, accent=game.accent)
        draw_bottom_rule(pygame, surface, height - 44, width)
        draw_text(surface, "GAME MODULE PLACEHOLDER", fonts.small, theme.TEXT_MUTED, (48, height - 32))
