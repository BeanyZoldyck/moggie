from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.config import load_config
from app.core.screen_manager import ScreenManager
from app.db import connect, initialize_database
from app.games.emoji_face_match import SUPPORTED_EXPRESSIONS
from app.services.leaderboard_service import LeaderboardService
from app.ui.screens.instruction_screen import emoji_instruction_expressions


class FakeCVService:
    def __init__(self) -> None:
        self.calls: list[tuple[bool | None, bool | None]] = []

    def configure_detection(self, *, hands: bool | None = None, faces: bool | None = None) -> None:
        self.calls.append((hands, faces))


class FakePygame:
    KEYDOWN = 1
    K_ESCAPE = 27
    K_TAB = 9
    K_DOWN = 274
    K_UP = 273
    K_RETURN = 13
    K_KP_ENTER = 271
    K_BACKSPACE = 8
    K_SPACE = 32
    K_LEFT = 276
    K_RIGHT = 275
    K_UP = 273
    K_DOWN = 274
    K_TAB = 9
    K_a = 97
    K_d = 100
    K_i = 105
    K_l = 108
    K_s = 115
    K_w = 119


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
        self.assertEqual(manager.state.player_names, ["P1", "P2"])
        self.assertEqual(
            [row["display_name"] for row in manager.state.reveal_rows],
            ["P1", "P2"],
        )

    def test_player_setup_first_typed_character_starts_name(self) -> None:
        manager = self._manager()
        manager.state.player_names = ["Old One", "Old Two"]
        manager.go_to("player_setup")

        screen = manager.active
        with patch("app.ui.screens.player_setup_screen._pygame", return_value=FakePygame):
            screen.handle_event(SimpleNamespace(type=FakePygame.KEYDOWN, key=FakePygame.K_a, unicode="A"))

        self.assertEqual(screen.values[0], "A")

    def test_home_i_opens_instructions_for_hovered_game(self) -> None:
        manager = self._manager()

        with patch("app.ui.screens.home_screen._pygame", return_value=FakePygame):
            manager.active.handle_event(SimpleNamespace(type=FakePygame.KEYDOWN, key=FakePygame.K_RIGHT, unicode=""))
            manager.active.handle_event(SimpleNamespace(type=FakePygame.KEYDOWN, key=FakePygame.K_i, unicode="i"))

        self.assertEqual(manager.current_screen, "instructions")
        self.assertEqual(manager.state.selected_game_type, "sixty_seven")
        self.assertEqual(manager.active.return_screen, "home")

    def test_player_setup_i_opens_instructions(self) -> None:
        manager = self._manager()
        manager.state.selected_game_type = "emoji_face_match"
        manager.go_to("player_setup")

        setup = manager.active
        setup.values = ["Ivy", "Jules"]
        setup.edited_fields = [True, True]
        setup.active_field = 1
        with patch("app.ui.screens.player_setup_screen._pygame", return_value=FakePygame):
            setup.handle_event(SimpleNamespace(type=FakePygame.KEYDOWN, key=FakePygame.K_i, unicode="i"))

        self.assertEqual(manager.current_screen, "instructions")
        self.assertEqual(manager.active.return_screen, "player_setup")
        with patch("app.ui.screens.instruction_screen._pygame", return_value=FakePygame):
            manager.active.handle_event(SimpleNamespace(type=FakePygame.KEYDOWN, key=FakePygame.K_i, unicode="i"))

        self.assertEqual(manager.current_screen, "player_setup")
        self.assertEqual(manager.active.values, ["Ivy", "Jules"])
        self.assertEqual(manager.active.edited_fields, [True, True])
        self.assertEqual(manager.active.active_field, 1)

    def test_emoji_instructions_cover_supported_expressions(self) -> None:
        self.assertEqual(set(emoji_instruction_expressions()), set(SUPPORTED_EXPRESSIONS))

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

    def test_cv_work_is_limited_to_active_game_need(self) -> None:
        config = load_config(
            {
                "MOGGIE_DB_PATH": str(self.db_path),
                "MOGGIE_ENABLE_REDIS_LEADERBOARD_CACHE": "false",
            }
        )
        cv_service = FakeCVService()
        manager = ScreenManager(config, LeaderboardService(config.db_path), cv_service=cv_service)

        manager.go_to("instructions")
        manager.go_to("sixty_seven")
        manager.state.selected_game_type = "mog_mirror"
        manager.go_to("player_setup")
        manager.go_to("mog_mirror")
        manager.go_to("emoji_face_match")
        manager.go_to("home")

        self.assertEqual(
            cv_service.calls,
            [
                (False, False),
                (False, False),
                (True, False),
                (False, False),
                (False, True),
                (False, True),
                (False, False),
            ],
        )

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

    def test_emoji_feedback_uses_target_label_not_noisy_detected_label(self) -> None:
        manager = self._manager({"MOGGIE_EMOJI_MODE": "solo"})
        manager.state.selected_game_type = "emoji_face_match"
        manager.state.player_names = ["Ivy"]
        manager.go_to("emoji_face_match")

        screen = manager.active
        lane = screen.lanes[0]
        lane.face = {"expression_features": {"tongue_out": 0.9, "mouth_open": 0.4}}
        lane.targets = [type("Target", (), {"expression": "smile", "spawn_ms": 0, "scored": False})()]

        screen._score_due_targets(lane, now_ms=10_000)

        self.assertEqual(lane.feedback, "MISS SMILE")

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

    def test_home_stays_on_home_when_idle_attract_is_disabled(self) -> None:
        manager = self._manager({"MOGGIE_IDLE_TIMEOUT_SECONDS": "5"})

        manager.update(now_ms=1_000, dt_ms=16)
        manager.update(now_ms=6_100, dt_ms=16)

        self.assertEqual(manager.current_screen, "home")

    def test_home_can_still_idle_into_attract_mode_when_enabled(self) -> None:
        manager = self._manager({"MOGGIE_IDLE_ATTRACT_ENABLED": "true", "MOGGIE_IDLE_TIMEOUT_SECONDS": "5"})

        manager.update(now_ms=1_000, dt_ms=16)
        manager.update(now_ms=6_100, dt_ms=16)

        self.assertEqual(manager.current_screen, "idle_attract")
        manager.wake_to_home()
        self.assertEqual(manager.current_screen, "home")

    def test_recent_media_assets_returns_generated_media_for_attract_mode(self) -> None:
        service = LeaderboardService(self.db_path)
        session = service.create_session("mog_mirror")
        player = service.get_or_create_player("Mina")
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO media_assets (
                    id, session_id, player_id, kind, storage_mode, uri, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "media_test",
                    session.id,
                    player.id,
                    "generated_clip",
                    "local",
                    "media/generated/mirror.mp4",
                    None,
                    "2026-06-20T12:00:00Z",
                ),
            )
            connection.commit()

        rows = service.recent_media_assets()

        self.assertEqual(rows[0]["kind"], "generated_clip")
        self.assertEqual(rows[0]["game_type"], "mog_mirror")
        self.assertEqual(rows[0]["display_name"], "Mina")


if __name__ == "__main__":
    unittest.main()
