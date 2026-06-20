from __future__ import annotations

from typing import Any

from app.core.game_catalog import GAMES, game_for_type
from app.ui import theme
from app.ui.render_utils import (
    FontSet,
    build_fonts,
    draw_badge,
    draw_bottom_rule,
    draw_panel,
    draw_text,
    draw_wrapped_text,
)


def _pygame() -> Any:
    import pygame

    return pygame


class IdleAttractScreen:
    name = "idle_attract"

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.fonts: FontSet | None = None
        self.entered_at_ms = 0
        self.game_index = 0
        self.leaderboard_rows: list[dict[str, Any]] = []
        self.media_rows: list[dict[str, Any]] = []

    def on_enter(self, **_: Any) -> None:
        self.entered_at_ms = 0
        self.game_index = 0
        self._refresh()

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type in {pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.JOYBUTTONDOWN}:
            self.manager.wake_to_home()

    def handle_app_event(self, event: Any) -> None:
        return None

    def update(self, now_ms: int, dt_ms: int) -> None:
        if self.entered_at_ms == 0:
            self.entered_at_ms = now_ms
        rotation_ms = self.manager.config.attract_rotation_seconds * 1000
        self.game_index = ((now_ms - self.entered_at_ms) // rotation_ms) % len(GAMES)

    def render(self, surface: Any) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        fonts = self.fonts
        width, height = surface.get_size()
        surface.fill(theme.BACKGROUND)

        game = GAMES[int(self.game_index)]
        pygame.draw.rect(surface, (31, 24, 24), pygame.Rect(0, 0, width, 136))
        pygame.draw.rect(surface, game.accent, pygame.Rect(0, 136, width, 5))
        draw_text(surface, "MOGGIE", fonts.masthead, theme.TEXT, (48, 22), max_width=width - 96)
        draw_text(
            surface,
            "STEP INTO YOUR LANE",
            fonts.body,
            game.accent,
            (width - 54, 82),
            anchor="topright",
            max_width=width // 2,
        )

        left_rect = pygame.Rect(54, 178, max(360, width // 2 - 82), height - 286)
        right_rect = pygame.Rect(left_rect.right + 28, 178, width - left_rect.right - 82, height - 286)
        self._render_game_card(pygame, surface, left_rect, game, fonts)
        self._render_scoreboard(pygame, surface, right_rect, game.game_type, fonts)

        media_rect = pygame.Rect(54, height - 88, width - 108, 42)
        self._render_media_strip(pygame, surface, media_rect, fonts)
        draw_bottom_rule(pygame, surface, height - 30, width)
        draw_text(
            surface,
            "PRESS ANY KEY TO PLAY",
            fonts.small,
            theme.TEXT_MUTED,
            (width // 2, height - 24),
            anchor="center",
            max_width=width - 96,
        )

    def _render_game_card(self, pygame: Any, surface: Any, rect: Any, game: Any, fonts: FontSet) -> None:
        draw_panel(pygame, surface, rect, fill=theme.SURFACE, border=game.accent, width=3)
        draw_badge(
            pygame,
            surface,
            pygame.Rect(rect.left + 28, rect.top + 28, 96, 36),
            game.badge,
            fonts.small,
            accent=game.accent,
        )
        draw_text(
            surface,
            game.title.upper(),
            fonts.title,
            theme.TEXT,
            (rect.left + 28, rect.top + 90),
            max_width=rect.width - 56,
        )
        draw_wrapped_text(
            surface,
            game.tagline,
            fonts.body,
            theme.TEXT_MUTED,
            pygame.Rect(rect.left + 30, rect.top + 166, rect.width - 60, 100),
            max_lines=2,
        )
        lane_y = rect.bottom - 102
        pygame.draw.line(surface, theme.DIM_BORDER, (rect.left + 30, lane_y), (rect.right - 30, lane_y), 2)
        pygame.draw.line(surface, game.accent, (rect.centerx, lane_y - 28), (rect.centerx, rect.bottom - 34), 4)
        draw_text(surface, "PLAYER 1", fonts.mono, theme.TEXT, (rect.left + 44, lane_y + 20))
        draw_text(surface, "PLAYER 2", fonts.mono, theme.TEXT, (rect.right - 44, lane_y + 20), anchor="topright")

    def _render_scoreboard(
        self,
        pygame: Any,
        surface: Any,
        rect: Any,
        game_type: str,
        fonts: FontSet,
    ) -> None:
        game = game_for_type(game_type)
        draw_panel(pygame, surface, rect, fill=theme.SURFACE_DARK, border=theme.BORDER, width=2)
        draw_text(surface, "TOP SCORES", fonts.card_title, theme.TEXT, (rect.left + 24, rect.top + 22))
        draw_text(surface, game.title, fonts.small, game.accent, (rect.left + 26, rect.top + 66))
        rows = [row for row in self.leaderboard_rows if row.get("game_type") == game_type]
        if not rows:
            draw_text(surface, "NO SCORES YET", fonts.body, theme.TEXT_MUTED, rect.center, anchor="center")
            return
        row_y = rect.top + 116
        for rank, row in enumerate(rows[:5], start=1):
            y = row_y + (rank - 1) * 48
            draw_text(surface, f"#{rank}", fonts.mono, game.accent, (rect.left + 28, y))
            draw_text(
                surface,
                str(row["display_name"]),
                fonts.body,
                theme.TEXT,
                (rect.left + 86, y - 4),
                max_width=rect.width - 220,
            )
            draw_text(
                surface,
                str(row["score"]),
                fonts.mono,
                theme.TEXT,
                (rect.right - 28, y),
                anchor="topright",
            )

    def _render_media_strip(self, pygame: Any, surface: Any, rect: Any, fonts: FontSet) -> None:
        draw_panel(pygame, surface, rect, fill=(26, 22, 25), border=theme.DIM_BORDER, width=1, radius=6)
        if not self.manager.config.save_generated_media:
            message = "LOCAL DEMO MODE: CLOUD MEDIA SAVING OFF"
        elif not self.media_rows:
            message = "GENERATED CLIPS WILL APPEAR HERE AFTER ROUNDS"
        else:
            labels = [f"{row.get('game_type', 'media')}:{row.get('kind', 'asset')}" for row in self.media_rows[:4]]
            message = "RECENT GENERATED MEDIA  " + "  /  ".join(labels)
        draw_text(surface, message.upper(), fonts.small, theme.TEXT_MUTED, rect.center, anchor="center", max_width=rect.width - 24)

    def _refresh(self) -> None:
        rows: list[dict[str, Any]] = []
        for game in GAMES:
            try:
                for row in self.manager.leaderboard_service.top_scores(game.game_type, limit=5):
                    rows.append({"game_type": game.game_type, **row})
            except Exception:
                continue
        self.leaderboard_rows = rows
        if self.manager.config.save_generated_media:
            try:
                self.media_rows = self.manager.leaderboard_service.recent_media_assets(limit=4)
            except Exception:
                self.media_rows = []
        else:
            self.media_rows = []
