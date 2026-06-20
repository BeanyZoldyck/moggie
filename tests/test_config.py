from __future__ import annotations

import unittest

from app.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_uses_safe_defaults(self) -> None:
        config = load_config({})

        self.assertEqual(config.env, "development")
        self.assertEqual(config.display_size, (1280, 720))
        self.assertEqual(config.zone_split_x, 0.5)
        self.assertEqual(config.sixty_seven_max_hands, 4)

    def test_invalid_enum_fails_fast(self) -> None:
        with self.assertRaises(ConfigError):
            load_config({"MOGGIE_DEFAULT_GAME_MODE": "chaos"})

    def test_numeric_values_are_clamped(self) -> None:
        config = load_config({"MOGGIE_CV_FPS": "999", "MOGGIE_ZONE_SPLIT_X": "2"})

        self.assertEqual(config.cv_fps, 60)
        self.assertEqual(config.zone_split_x, 0.95)


if __name__ == "__main__":
    unittest.main()
