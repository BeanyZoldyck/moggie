import unittest
from dataclasses import dataclass

from app.ui.renderers.camera_preview_renderer import CameraPreviewRenderer
from ui.moggi.screens.game_logic import normalize_winner


@dataclass
class RectStub:
    left: int
    top: int
    width: int
    height: int


class SixSevenRenderingTests(unittest.TestCase):
    def test_win_screen_derives_winner_when_result_is_stale_tie(self) -> None:
        self.assertEqual(normalize_winner("tie", 9, 4), "player_one")
        self.assertEqual(normalize_winner("draw", 3, 8), "player_two")
        self.assertEqual(normalize_winner("tie", 5, 5), "tie")

    def test_win_screen_accepts_common_winner_aliases(self) -> None:
        self.assertEqual(normalize_winner("p1", 0, 0), "player_one")
        self.assertEqual(normalize_winner("player 2", 0, 0), "player_two")

    def test_camera_point_mapping_accounts_for_split_crop(self) -> None:
        renderer = CameraPreviewRenderer()
        renderer.preview_regions = [
            {
                "zone": "p1",
                "source": (0.0, 0.0, 0.5, 1.0),
                "source_size": (320, 480),
                "crop": (0, 120, 320, 240),
                "dest": RectStub(40, 75, 594, 420),
            }
        ]

        self.assertEqual(
            renderer.point_to_screen({"x": 0.25, "y": 0.5}, zone="p1"),
            (337, 285),
        )
        self.assertEqual(
            renderer.point_to_screen({"x": 0.25, "y": 0.25}, zone="p1"),
            (337, 75),
        )


if __name__ == "__main__":
    unittest.main()
