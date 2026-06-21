from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.games.mog_mirror import crop_upper_body, label_for_aura, score_aura
from app.ui.screens.mog_mirror_screen import MirrorLane, MogMirrorScreen


class FakeFrame:
    def __init__(self, width: int, height: int) -> None:
        self.shape = (height, width, 3)

    def __getitem__(self, key: tuple[slice, slice]) -> "FakeFrame":
        y_slice, x_slice = key
        top = y_slice.start or 0
        bottom = y_slice.stop or self.shape[0]
        left = x_slice.start or 0
        right = x_slice.stop or self.shape[1]
        return FakeFrame(right - left, bottom - top)

    def copy(self) -> "FakeFrame":
        return FakeFrame(self.shape[1], self.shape[0])


class MogMirrorTests(unittest.TestCase):
    def test_aura_score_is_deterministic_and_playful_range(self) -> None:
        face = {
            "confidence": 0.9,
            "center": {"x": 0.25, "y": 0.35},
            "bbox": {"x": 0.18, "y": 0.18, "width": 0.16, "height": 0.24},
        }

        first = score_aura(session_id="session-1", display_name="Mina", zone="p1", face=face)
        second = score_aura(session_id="session-1", display_name="Mina", zone="p1", face=face)

        self.assertEqual(first, second)
        self.assertGreaterEqual(first, 45)
        self.assertLessEqual(first, 90)

    def test_aura_score_uses_sensitive_face_geometry(self) -> None:
        symmetrical = _mog_face()
        asymmetrical = _mog_face(offset=0.08)

        balanced_score = score_aura(session_id="session-geometry", display_name="Mina", zone="p1", face=symmetrical)
        asymmetrical_score = score_aura(session_id="session-geometry", display_name="Mina", zone="p1", face=asymmetrical)

        self.assertGreater(balanced_score, asymmetrical_score)

    def test_live_aura_score_fluctuates_wildly_by_sample_time(self) -> None:
        face = _mog_face()

        samples = [
            score_aura(session_id="session-live", display_name="Mina", zone="p1", face=face, sample_ms=sample_ms)
            for sample_ms in range(0, 5_000, 500)
        ]

        self.assertGreaterEqual(max(samples) - min(samples), 20)

    def test_missing_face_uses_mystery_label(self) -> None:
        self.assertEqual(label_for_aura(72, winner=False, face_detected=False), "MYSTERY AURA")

    def test_crop_upper_body_falls_back_to_player_zone_without_face(self) -> None:
        frame = FakeFrame(640, 480)

        crop = crop_upper_body(frame, None, "p2")

        self.assertIsNotNone(crop)
        assert crop is not None
        self.assertEqual(crop.shape, (480, 320, 3))

    def test_ai_submission_respects_disabled_cloud_flags(self) -> None:
        service = FakeAIJobService()
        screen = MogMirrorScreen(
            SimpleNamespace(
                ai_job_service=service,
                config=SimpleNamespace(enable_image_generation=False, enable_pika=False),
            )
        )

        job_ids = screen._submit_ai_jobs(MirrorLane(name="Mina", zone="p1"), None, 88, "MOGGED OUT")

        self.assertEqual(job_ids, [])
        self.assertEqual(service.submitted, [])

    def test_ai_submission_sends_original_crop_to_pika_when_enabled(self) -> None:
        service = FakeAIJobService()
        screen = MogMirrorScreen(
            SimpleNamespace(
                ai_job_service=service,
                config=SimpleNamespace(enable_image_generation=True, enable_pika=True),
            )
        )

        with patch("app.ui.screens.mog_mirror_screen.encode_bgr_jpeg", return_value=b"jpeg"):
            job_ids = screen._submit_ai_jobs(MirrorLane(name="Mina", zone="p1"), object(), 88, "MOGGED OUT")

        self.assertEqual(job_ids, ["job-1"])
        self.assertEqual([kind for kind, _ in service.submitted], ["mog_mirror.victory_video"])
        self.assertTrue(all(payload["has_crop"] for _, payload in service.submitted))
        self.assertIn("image_bytes", service.submitted[0][1])
        self.assertIn("prompt", service.submitted[0][1])

    def test_live_score_window_runs_for_ten_seconds(self) -> None:
        screen = MogMirrorScreen(SimpleNamespace())

        self.assertEqual(screen.live_score_duration_ms, 10_000)
        self.assertEqual(screen.countdown_ms, 10_000)

    def test_live_scores_refresh_every_half_second(self) -> None:
        screen = MogMirrorScreen(SimpleNamespace())
        screen.session_id = "session-1"
        screen.manual_override = False
        screen.lanes = [MirrorLane(name="Mina", zone="p1")]

        screen._update_live_scores(1_000)
        first_score = screen.lanes[0].live_score
        first_update = screen.lanes[0].live_score_updated_at_ms

        screen.lanes[0].face = {
            "confidence": 1.0,
            "center": {"x": 0.25, "y": 0.35},
            "bbox": {"x": 0.18, "y": 0.18, "width": 0.2, "height": 0.3},
        }
        screen._update_live_scores(1_499)

        self.assertEqual(screen.lanes[0].live_score, first_score)
        self.assertEqual(screen.lanes[0].live_score_updated_at_ms, first_update)

        screen._update_live_scores(1_500)

        self.assertNotEqual(screen.lanes[0].live_score, first_score)
        self.assertEqual(screen.lanes[0].live_score_updated_at_ms, 1_500)

    def test_final_score_uses_average_live_score(self) -> None:
        screen = MogMirrorScreen(SimpleNamespace())
        lane = MirrorLane(name="Mina", zone="p1", live_score=90)
        lane.live_score_samples.extend([40, 70, 91])

        self.assertEqual(screen._average_live_score(lane), 67)


def _mog_face(offset: float = 0.0) -> dict[str, object]:
    return {
        "confidence": 1.0,
        "center": {"x": 0.25, "y": 0.38},
        "bbox": {"x": 0.12, "y": 0.18, "width": 0.26, "height": 0.36},
        "landmarks": {
            "left_eye_outer": {"x": 0.17, "y": 0.30},
            "left_eye_inner": {"x": 0.22, "y": 0.30},
            "right_eye_inner": {"x": 0.28 + offset, "y": 0.30},
            "right_eye_outer": {"x": 0.33 + offset, "y": 0.30},
            "mouth_left": {"x": 0.19, "y": 0.49},
            "mouth_right": {"x": 0.31 + offset, "y": 0.49},
            "nose_tip": {"x": 0.25 + offset, "y": 0.39},
            "chin": {"x": 0.25 + offset, "y": 0.61},
            "left_cheek": {"x": 0.14, "y": 0.42},
            "right_cheek": {"x": 0.36 + offset, "y": 0.42},
        },
    }


@dataclass
class FakeAIJobService:
    submitted: list[tuple[str, dict[str, object]]] | None = None

    def __post_init__(self) -> None:
        self.submitted = []

    def submit(self, kind: str, payload: dict[str, object]) -> str:
        assert self.submitted is not None
        self.submitted.append((kind, payload))
        return f"job-{len(self.submitted)}"


if __name__ == "__main__":
    unittest.main()
