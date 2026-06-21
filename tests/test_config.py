from __future__ import annotations

import unittest

from app.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_uses_safe_defaults(self) -> None:
        config = load_config({})

        self.assertEqual(config.env, "development")
        self.assertEqual(config.display_size, (1280, 720))
        self.assertEqual(config.target_fps, 30)
        self.assertEqual(config.zone_split_x, 0.5)
        self.assertEqual(config.sixty_seven_max_hands, 4)
        self.assertEqual(config.sixty_seven_extend_threshold, 0.34)
        self.assertEqual(config.sixty_seven_return_threshold, 0.30)
        self.assertEqual(config.sixty_seven_min_swing, 0.04)
        self.assertEqual(config.camera_fps, 30)
        self.assertEqual(config.camera_retry_seconds, 3)
        self.assertTrue(config.idle_attract_enabled)
        self.assertEqual(config.idle_timeout_seconds, 90)
        self.assertEqual(config.attract_rotation_seconds, 8)

    def test_invalid_enum_fails_fast(self) -> None:
        with self.assertRaises(ConfigError):
            load_config({"MOGGIE_DEFAULT_GAME_MODE": "chaos"})

    def test_numeric_values_are_clamped(self) -> None:
        config = load_config({"MOGGIE_TARGET_FPS": "999", "MOGGIE_CV_FPS": "999", "MOGGIE_ZONE_SPLIT_X": "2"})

        self.assertEqual(config.target_fps, 120)
        self.assertEqual(config.cv_fps, 60)
        self.assertEqual(config.zone_split_x, 0.95)

    def test_sixty_seven_thresholds_are_configurable(self) -> None:
        config = load_config(
            {
                "MOGGIE_67_EXTEND_THRESHOLD": "0.30",
                "MOGGIE_67_RETURN_THRESHOLD": "0.27",
                "MOGGIE_67_MIN_SWING": "0.02",
            }
        )

        self.assertEqual(config.sixty_seven_extend_threshold, 0.30)
        self.assertEqual(config.sixty_seven_return_threshold, 0.27)
        self.assertEqual(config.sixty_seven_min_swing, 0.02)


if __name__ == "__main__":
    unittest.main()
