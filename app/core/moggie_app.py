from __future__ import annotations

import logging
from typing import Any

from app.config import MoggieConfig
from app.core.screen_manager import ScreenManager
from app.services.leaderboard_service import LeaderboardService

LOGGER = logging.getLogger(__name__)


def _pygame() -> Any:
    import pygame

    return pygame


class MoggieApp:
    target_fps = 30

    def __init__(self, config: MoggieConfig) -> None:
        self.config = config
        self.leaderboard_service = LeaderboardService.from_config(config)
        self.screen_manager = ScreenManager(config, self.leaderboard_service)
        self.running = False

    def run(self, frames: int | None = None) -> None:
        pygame = _pygame()
        max_frames = self.config.placeholder_frames if frames is None else max(0, frames)
        pygame.init()
        pygame.display.set_caption("Moggie")
        flags = pygame.FULLSCREEN if self.config.fullscreen else pygame.RESIZABLE
        surface = pygame.display.set_mode(self.config.display_size, flags)
        clock = pygame.time.Clock()
        frame_count = 0
        self.running = True

        LOGGER.info(
            "Starting Moggie app env=%s fullscreen=%s size=%sx%s",
            self.config.env,
            self.config.fullscreen,
            surface.get_width(),
            surface.get_height(),
        )

        try:
            while self.running and (max_frames == 0 or frame_count < max_frames):
                dt_ms = clock.tick(self.target_fps)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif self._is_quit_shortcut(event, pygame):
                        self.running = False
                    elif event.type == pygame.VIDEORESIZE and not self.config.fullscreen:
                        surface = pygame.display.set_mode((event.w, event.h), flags)
                    else:
                        self.screen_manager.handle_event(event)

                self.screen_manager.update(pygame.time.get_ticks(), dt_ms)
                self.screen_manager.render(surface)
                pygame.display.flip()

                if self.screen_manager.should_quit:
                    self.running = False
                frame_count += 1
        finally:
            pygame.quit()
            LOGGER.info("Moggie app exited after %s frame(s)", frame_count)

    def _is_quit_shortcut(self, event: Any, pygame: Any) -> bool:
        if event.type != pygame.KEYDOWN or event.key != pygame.K_q:
            return False
        return bool(event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META))
