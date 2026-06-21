from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        self.assertEqual(config.camera_gain, 1.0)
        self.assertEqual(config.camera_brightness, 0)
        self.assertEqual(config.camera_backend, "opencv")
        self.assertEqual(config.camera_retry_seconds, 3)
        self.assertEqual(config.qnx_camera_unit, 1)
        self.assertEqual(config.qnx_camera_decimate, 3)
        self.assertTrue(config.cv_enable_face_detection)
        self.assertEqual(config.hand_tracking_backend, "mediapipe")
        self.assertEqual(config.face_tracking_backend, "mediapipe")
        self.assertTrue(config.idle_attract_enabled)
        self.assertEqual(config.idle_timeout_seconds, 90)
        self.assertEqual(config.attract_rotation_seconds, 8)
        self.assertFalse(config.enable_s3_video_storage)
        self.assertEqual(config.s3_bucket, "")
        self.assertEqual(config.s3_region, "")
        self.assertEqual(config.s3_prefix, "")
        self.assertFalse(config.enable_social_posting)
        self.assertEqual(config.default_post_platform, "x")
        self.assertEqual(config.x_api_key, "")
        self.assertEqual(config.x_api_key_secret, "")
        self.assertEqual(config.x_access_token, "")
        self.assertEqual(config.x_access_token_secret, "")

    def test_invalid_enum_fails_fast(self) -> None:
        with self.assertRaises(ConfigError):
            load_config({"MOGGIE_DEFAULT_GAME_MODE": "chaos"})

        with self.assertRaises(ConfigError):
            load_config({"MOGGIE_CAMERA_BACKEND": "raspicam"})
        with self.assertRaises(ConfigError):
            load_config({"MOGGIE_HAND_TRACKING_BACKEND": "magic"})
        with self.assertRaises(ConfigError):
            load_config({"MOGGIE_FACE_TRACKING_BACKEND": "magic"})

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

    def test_load_config_reads_local_dotenv_without_overriding_environment(self) -> None:
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"MOGGIE_TARGET_FPS": "24"}, clear=True):
            os.chdir(tmp)
            try:
                Path(".env").write_text(
                    "MOGGIE_TARGET_FPS=60\n"
                    "MOGGIE_REDIS_URL='redis://default:secret@example.redis:13364/0'\n",
                    encoding="utf-8",
                )

                config = load_config()
            finally:
                os.chdir(cwd)

        self.assertEqual(config.target_fps, 24)
        self.assertEqual(config.redis_url, "redis://default:secret@example.redis:13364/0")

    def test_s3_values_are_loaded_when_present(self) -> None:
        config = load_config(
            {
                "MOGGIE_ENABLE_S3_VIDEO_STORAGE": "true",
                "MOGGIE_S3_BUCKET": "moggie-videos",
                "MOGGIE_S3_REGION": "us-east-1",
                "MOGGIE_S3_PREFIX": "hackathon",
            }
        )

        self.assertTrue(config.enable_s3_video_storage)
        self.assertEqual(config.s3_bucket, "moggie-videos")
        self.assertEqual(config.s3_region, "us-east-1")
        self.assertEqual(config.s3_prefix, "hackathon")

    def test_social_posting_values_are_loaded_when_present(self) -> None:
        config = load_config(
            {
                "MOGGIE_ENABLE_SOCIAL_POSTING": "true",
                "MOGGIE_DEFAULT_POST_PLATFORM": "x",
                "X_API_KEY": "abc",
                "X_API_KEY_SECRET": "def",
                "X_ACCESS_TOKEN": "ghi",
                "X_ACCESS_TOKEN_SECRET": "jkl",
                "MOGGIE_DEEPGRAM_VOICE_AGENT_ENDPOINT": "wss://agent.deepgram.com/v1/agent/converse",
            }
        )
        self.assertTrue(config.enable_social_posting)
        self.assertEqual(config.default_post_platform, "x")
        self.assertEqual(config.x_api_key, "abc")
        self.assertEqual(config.x_api_key_secret, "def")
        self.assertEqual(config.x_access_token, "ghi")
        self.assertEqual(config.x_access_token_secret, "jkl")
        self.assertEqual(config.deepgram_voice_agent_endpoint, "wss://agent.deepgram.com/v1/agent/converse")


if __name__ == "__main__":
    unittest.main()
