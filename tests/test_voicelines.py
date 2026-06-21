from __future__ import annotations

import unittest

from app.games.voicelines import MOG_MIRROR_END, pick_voiceline


class VoicelineTests(unittest.TestCase):
    def test_mog_mirror_end_pool_includes_brutal(self) -> None:
        self.assertIn("Brutal!", MOG_MIRROR_END)

    def test_pick_voiceline_returns_non_empty_for_known_game(self) -> None:
        line = pick_voiceline("mog_mirror", "end")
        self.assertTrue(line)

    def test_unknown_game_returns_empty(self) -> None:
        self.assertEqual(pick_voiceline("unknown_game", "end"), "")


if __name__ == "__main__":
    unittest.main()
