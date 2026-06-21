from __future__ import annotations

import unittest

from app.games.voicelines import MOG_MIRROR_END, pick_voiceline


class VoicelineTests(unittest.TestCase):
    def test_mog_mirror_end_pool_includes_brutal(self) -> None:
        self.assertIn("Brutal!", MOG_MIRROR_END)

    def test_pick_voiceline_returns_non_empty_for_known_game(self) -> None:
        line = pick_voiceline("mog_mirror", "end")
        self.assertTrue(line)

    def test_all_games_have_substantial_pools(self) -> None:
        from app.games import voicelines as vl

        for game_type in ("mog_mirror", "sixty_seven", "emoji_face_match"):
            with self.subTest(game_type=game_type):
                self.assertGreaterEqual(len(vl._LINES[(game_type, "intro")]), 10)
                self.assertGreaterEqual(len(vl._LINES[(game_type, "end")]), 10)


if __name__ == "__main__":
    unittest.main()
