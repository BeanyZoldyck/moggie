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

        self.assertEqual(manager.current_screen, "mog_mirror")
        self.assertEqual(manager.state.player_names, ["Player 1", "Player 2"])
        self.assertEqual(
            [row["display_name"] for row in manager.state.reveal_rows],
            ["Player 1", "Player 2"],
        )

    def test_mog_mirror_setup_routes_to_gameplay_screen(self) -> None:
        manager = self._manager()
        manager.state.selected_game_type = "mog_mirror"
        manager.go_to("player_setup")

        screen = manager.active
        screen.values = ["Mina", "Nico"]
        screen._submit()

        self.assertEqual(manager.current_screen, "mog_mirror")
        self.assertEqual(manager.state.player_names, ["Mina", "Nico"])

    def test_mog_mirror_finish_persists_offline_scores_to_leaderboard(self) -> None:
        manager = self._manager()
        manager.state.selected_game_type = "mog_mirror"
        manager.state.player_names = ["Mina", "Nico"]
        manager.go_to("mog_mirror")

        screen = manager.active
        screen.manual_override = True
        screen._finish_round()

        self.assertEqual(manager.current_screen, "score_reveal")
        self.assertEqual([row["display_name"] for row in manager.state.reveal_rows], ["Mina", "Nico"])
        self.assertTrue(all(isinstance(row["score"], int) for row in manager.state.reveal_rows))
        leaders = manager.leaderboard_service.top_scores("mog_mirror")
        self.assertEqual(len(leaders), 2)
        self.assertEqual({entry["display_name"] for entry in leaders}, {"Mina", "Nico"})

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

    def test_emoji_face_match_setup_routes_to_gameplay_screen(self) -> None:
        manager = self._manager()
        manager.state.selected_game_type = "emoji_face_match"
        manager.go_to("player_setup")

        screen = manager.active
        screen.values = ["Ivy", "Jules"]
        screen._submit()

        self.assertEqual(manager.current_screen, "emoji_face_match")
        self.assertEqual(manager.state.player_names, ["Ivy", "Jules"])

    def test_emoji_face_match_finish_persists_scores_to_leaderboard(self) -> None:
        manager = self._manager()
        manager.state.selected_game_type = "emoji_face_match"
        manager.state.player_names = ["Ivy", "Jules"]
        manager.go_to("emoji_face_match")

        screen = manager.active
        screen.lanes[0].score = 200
        screen.lanes[0].hits = 2
        screen.lanes[0].attempts = 3
        screen.lanes[1].score = 100
        screen.lanes[1].hits = 1
        screen.lanes[1].attempts = 3
        screen._finish_round()

        self.assertEqual(manager.current_screen, "score_reveal")
        self.assertEqual([row["score"] for row in manager.state.reveal_rows], [200, 100])
        leaders = manager.leaderboard_service.top_scores("emoji_face_match")
        self.assertEqual(leaders[0]["display_name"], "Ivy")
        self.assertEqual(leaders[0]["score"], 200)

    def test_solo_modes_use_one_name_field(self) -> None:
        manager = self._manager({"MOGGIE_67_MODE": "solo"})
        manager.state.selected_game_type = "sixty_seven"
        manager.go_to("player_setup")

        screen = manager.active

        self.assertEqual(screen.values, [""])

    def test_emoji_solo_mode_uses_one_name_field(self) -> None:
        manager = self._manager({"MOGGIE_EMOJI_MODE": "solo"})
        manager.state.selected_game_type = "emoji_face_match"
        manager.go_to("player_setup")

        screen = manager.active

        self.assertEqual(screen.values, [""])


if __name__ == "__main__":
    unittest.main()
