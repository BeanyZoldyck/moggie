from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import load_config
from app.core.screen_manager import ScreenManager
from app.db import initialize_database
from app.services.leaderboard_service import LeaderboardService


class ShellNavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "moggie.sqlite"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _manager(self, overrides: dict[str, str] | None = None) -> ScreenManager:
        env = {
            "MOGGIE_DB_PATH": str(self.db_path),
            "MOGGIE_ENABLE_REDIS_LEADERBOARD_CACHE": "false",
        }
        if overrides:
            env.update(overrides)
        config = load_config(env)
        return ScreenManager(config, LeaderboardService(config.db_path))

    def test_screen_manager_starts_on_home(self) -> None:
        manager = self._manager()

        self.assertEqual(manager.current_screen, "home")
        self.assertEqual(manager.state.selected_game_type, "mog_mirror")

    def test_player_setup_replaces_empty_names_with_safe_aliases(self) -> None:
        manager = self._manager()
        manager.go_to("player_setup")

        screen = manager.active
        screen.values = ["", "  "]
        screen._submit()

        self.assertEqual(manager.current_screen, "score_reveal")
        self.assertEqual(manager.state.player_names, ["Player 1", "Player 2"])
        self.assertEqual(
            [row["display_name"] for row in manager.state.reveal_rows],
            ["Player 1", "Player 2"],
        )

    def test_sixty_seven_setup_routes_to_gameplay_screen(self) -> None:
        manager = self._manager()
        manager.state.selected_game_type = "sixty_seven"
        manager.go_to("player_setup")

        screen = manager.active
        screen.values = ["Ada", "Ben"]
        screen._submit()

        self.assertEqual(manager.current_screen, "sixty_seven")
        self.assertEqual(manager.state.player_names, ["Ada", "Ben"])

    def test_sixty_seven_finish_persists_scores_to_leaderboard(self) -> None:
        manager = self._manager()
        manager.state.selected_game_type = "sixty_seven"
        manager.state.player_names = ["Ada", "Ben"]
        manager.go_to("sixty_seven")

        screen = manager.active
        screen.lanes[0].counter.reps = 4
        screen.lanes[1].counter.reps = 7
        screen._finish_round()

        self.assertEqual(manager.current_screen, "score_reveal")
        self.assertEqual([row["score"] for row in manager.state.reveal_rows], [4, 7])
        leaders = manager.leaderboard_service.top_scores("sixty_seven")
        self.assertEqual(leaders[0]["display_name"], "Ben")
        self.assertEqual(leaders[0]["score"], 7)

    def test_solo_modes_use_one_name_field(self) -> None:
        manager = self._manager({"MOGGIE_67_MODE": "solo"})
        manager.state.selected_game_type = "sixty_seven"
        manager.go_to("player_setup")

        screen = manager.active

        self.assertEqual(screen.values, [""])


if __name__ == "__main__":
    unittest.main()
