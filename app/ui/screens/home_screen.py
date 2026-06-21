from __future__ import annotations

import math
from typing import Any

from app.core.game_catalog import GAMES, game_index 
from app.ui import theme
from app.ui.render_utils import (
    FontSet,
    build_fonts,
    draw_badge,
    draw_bottom_rule,
    draw_button,
    draw_centered_asset,
    draw_panel,
    draw_text,
    draw_wrapped_text,
    scaled_asset_image,
)

def _pygame() -> Any:
    import pygame

    return pygame


class HomeScreen:
    name = "home"
    card_assets = (
        ("card_mirror.png", "card_mirror_selected.PNG"),
        ("card_sixseven.PNG", "card_sixseven_selected.PNG"),
        ("card_emoji.PNG", "card_emoji_selected.PNG"),
    )

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.game_index = 0
        self.action_index = 0
        self.fonts: FontSet | None = None

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
        bg = scaled_asset_image(pygame, "arcade_bg.png", (width, height))
        if bg is None:
            surface.fill(theme.BACKGROUND)
        else:
            surface.blit(bg, (0, 0))

        scale = min(width / 1280, height / 720)
        card_normal = (max(184, int(330 * scale)), max(262, int(470 * scale)))
        card_selected = (max(202, int(360 * scale)), max(292, int(520 * scale)))
        card_centers = (
            (int(width * 0.281), int(height * 0.493)),
            (int(width * 0.492), int(height * 0.493)),
            (int(width * 0.711), int(height * 0.493)),
        )
        for index, game in enumerate(GAMES):
            selected = index == self.game_index and self.action_index == 0
            normal_asset, selected_asset = self.card_assets[index]
            filename = selected_asset if selected else normal_asset
            size = card_selected if selected else card_normal
            rect = draw_centered_asset(pygame, surface, filename, card_centers[index], size)
            if rect is None:
                rect = self._render_fallback_card(pygame, surface, index, game, card_centers[index], size, fonts)

        active_game = GAMES[self.game_index]

        play_size = (
            max(190, int((350 if self.action_index == 0 else 320) * scale)),
            max(96, int((200 if self.action_index == 0 else 170) * scale)),
        )
        play_asset = "lets_go_pressed.png" if self.action_index == 0 else "lets_go.png"
        play_rect = draw_centered_asset(pygame, surface, play_asset, (width // 2, int(height * 0.75)), play_size)
        if play_rect is None:
            play_rect = pygame.Rect(width // 2 - 106, int(height * 0.75) - 29, 212, 58)
            draw_button(
                pygame,
                surface,
                play_rect,
                "PLAY",
                fonts.body,
                selected=self.action_index == 0,
                accent=active_game.accent,
            )

        board_rect = pygame.Rect(width - 210, height - 94, 154, 46)
        draw_button(
            pygame,
            surface,
            board_rect,
            "BOARD",
            fonts.body,
            selected=self.action_index == 1,
            accent=active_game.accent,
        )

        mascot_size = (max(110, int(300 * scale)), max(164, int(450 * scale)))
        bounce = int(math.sin(pygame.time.get_ticks() / 120) * 7 * scale)
        draw_centered_asset(
            pygame,
            surface,
            "moo_deng_pixel.png",
            (min(width - mascot_size[0] // 3, int(width * 0.88)), int(height * 0.70) + bounce),
            mascot_size,
        )

        draw_bottom_rule(pygame, surface, height - 34, width)
        draw_text(surface, "SPACE TO SELECT", fonts.small, theme.TEXT, (width // 2, height - 140), anchor="center")

    def _render_fallback_card(
        self,
        pygame: Any,
        surface: Any,
        index: int,
        game: Any,
        center: tuple[int, int],
        size: tuple[int, int],
        fonts: FontSet,
    ) -> Any:
        rect = pygame.Rect(0, 0, size[0], size[1])
        rect.center = center
        selected = index == self.game_index and self.action_index == 0
        fill = (39, 32, 35) if selected else theme.SURFACE
        border = game.accent if selected else theme.DIM_BORDER
        draw_panel(pygame, surface, rect, fill=fill, border=border, width=3 if selected else 1)
        badge_rect = pygame.Rect(rect.left + 22, rect.top + 24, 82, 32)
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
        return rect

    def _move_game(self, direction: int) -> None:
        self.game_index = (self.game_index + direction) % len(GAMES)
        self.manager.state.selected_game_type = GAMES[self.game_index].game_type

    def _activate_action(self) -> None:
        self.manager.state.selected_game_type = GAMES[self.game_index].game_type
        if self.action_index == 0:
            selected_game = GAMES[self.game_index].game_type

            if selected_game == "mog_mirror":
                self.manager.go_to("mog_mirror")
            elif selected_game == "sixty_seven":
                self.manager.go_to("sixty_seven")
            elif selected_game == "emoji_face_match":
                self.manager.go_to("emoji_face_match")
        else:
            self.manager.go_to("leaderboard")
