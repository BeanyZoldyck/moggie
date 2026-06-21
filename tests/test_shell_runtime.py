from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from app.config import load_config
from app.core.screen_manager import ScreenManager
from app.db import initialize_database
from app.services.leaderboard_service import LeaderboardService

HAS_PYGAME = importlib.util.find_spec("pygame") is not None


@unittest.skipUnless(HAS_PYGAME, "pygame runtime is not installed")
class ShellRuntimeTests(unittest.TestCase):
    pygame: Any

    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame

        cls.pygame = pygame
        pygame.init()
        pygame.display.set_mode((1280, 720))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.pygame.quit()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "moggie.sqlite"
        initialize_database(self.db_path)
        config = load_config(
            {
                "MOGGIE_DB_PATH": str(self.db_path),
                "MOGGIE_ENABLE_REDIS_LEADERBOARD_CACHE": "false",
            }
        )
        self.manager = ScreenManager(config, LeaderboardService(config.db_path))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_keyboard_flow_selects_game_enters_names_and_returns_home(self) -> None:
        pygame = self.pygame

        self.manager.handle_event(self._key(pygame.K_RIGHT))
        self.manager.handle_event(self._key(pygame.K_RETURN))
        self.assertEqual(self.manager.current_screen, "player_setup")
        self.assertEqual(self.manager.state.selected_game_type, "sixty_seven")

        for char in "Ada":
            self.manager.handle_event(self._key(ord(char.lower()), char))
        self.manager.handle_event(self._key(pygame.K_RETURN))
        for char in "Ben":
            self.manager.handle_event(self._key(ord(char.lower()), char))
        self.manager.handle_event(self._key(pygame.K_RETURN))

        self.assertEqual(self.manager.current_screen, "sixty_seven")
        self.assertEqual(self.manager.state.player_names, ["Ada", "Ben"])

        self.manager.handle_event(self._key(pygame.K_ESCAPE))
        self.assertEqual(self.manager.current_screen, "home")

        self.manager.handle_event(self._key(pygame.K_l, "l"))
        self.assertEqual(self.manager.current_screen, "leaderboard")

    def test_ticket_three_screens_render_with_real_pygame_surface(self) -> None:
        pygame = self.pygame
        surface = pygame.Surface((1280, 720))

        self.manager.render(surface)
        self.manager.go_to("player_setup")
        self.manager.render(surface)
        self.manager.active._submit()
        self.manager.render(surface)
        self.manager.go_to("leaderboard")
        self.manager.render(surface)
        self.manager.state.player_names = ["Ada", "Ben"]
        self.manager.go_to("emoji_face_match")
        self.manager.render(surface)
        self.manager.go_to("idle_attract")
        self.manager.update(10_000, 16)
        self.manager.render(surface)

    def _key(self, key: int, unicode: str = "") -> Any:
        return self.pygame.event.Event(self.pygame.KEYDOWN, key=key, unicode=unicode, mod=0)


if __name__ == "__main__":
    unittest.main()
