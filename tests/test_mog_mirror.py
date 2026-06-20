from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import unittest

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
        self.assertGreaterEqual(first, 65)
        self.assertLessEqual(first, 99)

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

    def test_ai_submission_skips_pika_without_public_source_url(self) -> None:
        service = FakeAIJobService()
        screen = MogMirrorScreen(
            SimpleNamespace(
                ai_job_service=service,
                config=SimpleNamespace(enable_image_generation=True, enable_pika=True),
            )
        )

        job_ids = screen._submit_ai_jobs(MirrorLane(name="Mina", zone="p1"), object(), 88, "MOGGED OUT")

        self.assertEqual(job_ids, ["job-1"])
        self.assertEqual([kind for kind, _ in service.submitted], ["mog_mirror.caricature"])
        self.assertTrue(all(payload["has_crop"] for _, payload in service.submitted))


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
