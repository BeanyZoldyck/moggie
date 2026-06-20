from __future__ import annotations

from typing import Any

from app.core.game_catalog import GAMES, game_index, player_count_for_game
from app.ui import theme
from app.ui.render_utils import (
    FontSet,
    build_fonts,
    draw_badge,
    draw_bottom_rule,
    draw_button,
    draw_panel,
    draw_text,
    draw_wrapped_text,
)
from app.ui.renderers.camera_preview_renderer import CameraPreviewRenderer


def _pygame() -> Any:
    import pygame

    return pygame


class HomeScreen:
    name = "home"

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.game_index = 0
        self.action_index = 0
        self.fonts: FontSet | None = None
        self.preview_renderer = CameraPreviewRenderer()

    def on_enter(self, **_: Any) -> None:
        self.game_index = game_index(self.manager.state.selected_game_type)
        self.action_index = 0

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type != pygame.KEYDOWN:
            return
        if event.key in {pygame.K_LEFT, pygame.K_a}:
            self._move_game(-1)
        elif event.key in {pygame.K_RIGHT, pygame.K_d}:
            self._move_game(1)
        elif event.key in {pygame.K_UP, pygame.K_DOWN, pygame.K_TAB, pygame.K_w, pygame.K_s}:
            self.action_index = 1 - self.action_index
        elif event.key in {pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE}:
            self._activate_action()
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

        pygame.draw.rect(surface, (31, 24, 24), pygame.Rect(0, 0, width, 126))
        pygame.draw.rect(surface, theme.ACCENT, pygame.Rect(0, 126, width, 4))
        draw_text(surface, "MOGGIE", fonts.masthead, theme.TEXT, (48, 24))
        draw_text(surface, "KIOSK PARTY SHELL", fonts.small, theme.TEXT_MUTED, (54, 96))

        card_margin = 48
        card_gap = 18
        card_y = 168
        preview_h = min(164, max(118, height // 5))
        card_h = min(276, max(218, height - preview_h - 392))
        card_w = (width - card_margin * 2 - card_gap * 2) // 3
        for index, game in enumerate(GAMES):
            rect = pygame.Rect(card_margin + index * (card_w + card_gap), card_y, card_w, card_h)
            selected = index == self.game_index
            fill = (39, 32, 35) if selected else theme.SURFACE
            border = game.accent if selected else theme.DIM_BORDER
            draw_panel(pygame, surface, rect, fill=fill, border=border, width=3 if selected else 1)
            pygame.draw.rect(
                surface,
                game.accent,
                pygame.Rect(rect.left + 18, rect.bottom - 18, rect.width - 36, 6),
                border_radius=3,
            )
            badge_rect = pygame.Rect(rect.left + 22, rect.top + 22, 82, 32)
            draw_badge(pygame, surface, badge_rect, game.badge, fonts.small, accent=game.accent)
            draw_text(
                surface,
                game.title,
                fonts.card_title,
                theme.TEXT,
                (rect.left + 22, rect.top + 78),
                max_width=rect.width - 44,
            )
            draw_wrapped_text(
                surface,
                game.tagline,
                fonts.body,
                theme.TEXT_MUTED,
                pygame.Rect(rect.left + 24, rect.top + 136, rect.width - 48, 94),
                max_lines=2,
            )
            player_count = player_count_for_game(game.game_type, self.manager.config)
            mode = "SOLO" if player_count == 1 else "1V1"
            draw_text(
                surface,
                mode,
                fonts.mono,
                game.accent if selected else theme.TEXT_MUTED,
                (rect.left + 24, rect.bottom - 58),
            )

        active_game = GAMES[self.game_index]
        preview_rect = pygame.Rect(48, min(height - preview_h - 64, card_y + card_h + 24), min(430, width - 96), preview_h)
        camera_service = self.manager.camera_service
        frame = camera_service.latest_display_frame() if camera_service is not None else None
        diagnostic = (
            camera_service.diagnostic_message
            if camera_service is not None
            else f"Camera index {self.manager.config.camera_index} is not configured."
        )
        self.preview_renderer.render(
            surface,
            preview_rect,
            frame_bgr=frame,
            diagnostic=diagnostic,
            show_divider=self.manager.config.show_zone_divider,
        )
        draw_text(surface, "LIVE CAMERA", fonts.small, theme.TEXT_MUTED, (preview_rect.right + 18, preview_rect.top + 6))
        draw_text(
            surface,
            f"INDEX {self.manager.config.camera_index}",
            fonts.mono,
            theme.ACCENT if frame is not None else theme.ERROR,
            (preview_rect.right + 18, preview_rect.top + 34),
        )

        button_w = 212
        button_h = 58
        buttons_y = height - 126
        play_rect = pygame.Rect(width // 2 - button_w - 12, buttons_y, button_w, button_h)
        board_rect = pygame.Rect(width // 2 + 12, buttons_y, button_w, button_h)
        draw_button(
            pygame,
            surface,
            play_rect,
            "PLAY",
            fonts.body,
            selected=self.action_index == 0,
            accent=active_game.accent,
        )
        draw_button(
            pygame,
            surface,
            board_rect,
            "BOARD",
            fonts.body,
            selected=self.action_index == 1,
            accent=active_game.accent,
        )
        draw_bottom_rule(pygame, surface, height - 44, width)
        draw_text(surface, "PYGAME / SQLITE / REDIS / OPTIONAL CLOUD AI", fonts.small, theme.TEXT_MUTED, (48, height - 32))

    def _move_game(self, direction: int) -> None:
        self.game_index = (self.game_index + direction) % len(GAMES)
        self.manager.state.selected_game_type = GAMES[self.game_index].game_type

    def _activate_action(self) -> None:
        self.manager.state.selected_game_type = GAMES[self.game_index].game_type
        if self.action_index == 0:
            self.manager.go_to("player_setup")
        else:
            self.manager.go_to("leaderboard")
