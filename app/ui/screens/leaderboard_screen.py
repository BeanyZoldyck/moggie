from __future__ import annotations

from typing import Any

from app.core.game_catalog import GAMES, game_for_type, game_index
from app.ui import theme
from app.ui.render_utils import (
    FontSet,
    build_fonts,
    draw_bottom_rule,
    draw_text,
    scaled_asset_image,
)


def _pygame() -> Any:
    import pygame

    return pygame


class LeaderboardScreen:
    name = "leaderboard"

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.fonts: FontSet | None = None
        self.game_index = 0
        self.entries: list[dict[str, Any]] = []
        self.error: str | None = None

    def on_enter(self, **_: Any) -> None:
        self.game_index = game_index(self.manager.state.selected_game_type)
        self._refresh()

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type != pygame.KEYDOWN:
            return
        if event.key in {pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_h}:
            self.manager.go_to("home")
        elif event.key in {pygame.K_LEFT, pygame.K_a}:
            self._move_game(-1)
        elif event.key in {pygame.K_RIGHT, pygame.K_d}:
            self._move_game(1)
        elif event.key in {pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE}:
            self.manager.go_to("player_setup")

    def update(self, now_ms: int, dt_ms: int) -> None:
        return None

    def render(self, surface: Any) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        fonts = self.fonts
        width, height = surface.get_size()
        bg = scaled_asset_image(pygame, "leaderboard_bg.png", (width, height))
        if bg is not None:
            surface.blit(bg, (0, 0))
        else:
            surface.fill(theme.BACKGROUND)

        game = game_for_type(self.manager.state.selected_game_type)

        table_rect = pygame.Rect(64, 162, width - 128, height - 276)
        header_y = table_rect.top + 26
        draw_text(surface, "RANK", fonts.small, theme.TEXT_MUTED, (table_rect.left + 200, header_y))
        draw_text(surface, "NAME", fonts.small, theme.TEXT_MUTED, (table_rect.left + 300, header_y))
        draw_text(surface, "SCORE", fonts.small, theme.TEXT_MUTED, (table_rect.right - 350, header_y), anchor="topright")
        pygame.draw.line(
            surface,
            theme.DIM_BORDER,
            (table_rect.left + 200, header_y + 34),
            (table_rect.right - 200, header_y + 34),
            1,
        )

        if self.error is not None:
            draw_text(surface, self.error, fonts.body, theme.ERROR, table_rect.center, anchor="center")
        elif not self.entries:
            draw_text(surface, "NO SCORES YET", fonts.body, theme.TEXT_MUTED, table_rect.center, anchor="center")
        else:
            row_y = header_y + 56
            row_h = 30
            for rank, entry in enumerate(self.entries[:10], start=1):
                y = row_y + (rank - 1) * row_h
                draw_text(surface, str(rank), fonts.mono, game.accent, (table_rect.left + 200, y))
                draw_text(
                    surface,
                    str(entry["display_name"]),
                    fonts.body,
                    theme.TEXT,
                    (table_rect.left + 300, y - 2),
                    max_width=table_rect.width - 310,
                )
                draw_text(
                    surface,
                    str(entry["score"]),
                    fonts.mono,
                    theme.TEXT,
                    (table_rect.right - 350, y),
                    anchor="topright",
                )

        draw_bottom_rule(pygame, surface, height - 44, width)
        draw_text(surface, "MOGGIE", fonts.small, theme.TEXT_MUTED, (48, height - 32))

    def _move_game(self, direction: int) -> None:
        self.game_index = (self.game_index + direction) % len(GAMES)
        self.manager.state.selected_game_type = GAMES[self.game_index].game_type
        self._refresh()

    def _refresh(self) -> None:
        self.error = None
        game_type = self.manager.state.selected_game_type
        try:
            self.entries = self.manager.leaderboard_service.top_scores(game_type)
        except Exception as exc:
            self.entries = []
            self.error = f"LEADERBOARD UNAVAILABLE: {exc}"
