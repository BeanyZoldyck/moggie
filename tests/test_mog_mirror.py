from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import unittest

from app.games.mog_mirror import build_replay_prompt, crop_upper_body, label_for_aura, score_aura
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

    def test_display_score_targets_use_five_round_buckets(self) -> None:
        screen = MogMirrorScreen(SimpleNamespace())
        screen.started_at_ms = 1_000

        buckets = [screen._display_target_bucket(now_ms) for now_ms in [1_000, 2_999, 3_000, 5_000, 7_000, 9_000, 10_999]]

        self.assertEqual(buckets, [0, 0, 1, 2, 3, 4, 4])

    def test_display_score_target_stays_in_one_to_one_hundred_range(self) -> None:
        screen = MogMirrorScreen(SimpleNamespace())
        screen.session_id = "session-1"
        screen.started_at_ms = 0
        lane = MirrorLane(name="Mina", zone="p1", live_score=100, face=_mog_face())
        lane.movement_energy = 1.0

        screen._set_display_target(lane, 0)

        self.assertGreaterEqual(lane.display_score_target, 1)
        self.assertLessEqual(lane.display_score_target, 100)
        self.assertEqual(lane.display_target_index, 0)

    def test_face_motion_increases_display_target(self) -> None:
        screen = MogMirrorScreen(SimpleNamespace())
        screen.session_id = "session-1"
        screen.started_at_ms = 0
        still = MirrorLane(name="Mina", zone="p1", live_score=60, face=_mog_face())
        moving = MirrorLane(name="Mina", zone="p1", live_score=60, face=_mog_face())

        screen._update_lane_movement(moving)
        moving.face = _mog_face(center_x=0.36, center_y=0.46, width=0.31)
        screen._update_lane_movement(moving)
        screen._set_display_target(still, 0)
        screen._set_display_target(moving, 0)

        self.assertGreater(moving.movement_energy, 0)
        self.assertGreater(moving.display_score_target, still.display_score_target)

    def test_final_score_uses_average_live_score(self) -> None:
        screen = MogMirrorScreen(SimpleNamespace())
        lane = MirrorLane(name="Mina", zone="p1", live_score=90)
        lane.live_score_samples.extend([40, 70, 91])

        self.assertEqual(screen._average_live_score(lane), 67)


class MogMirrorFinishTests(unittest.TestCase):
    def test_finish_stashes_both_sides_frame_and_does_not_submit(self) -> None:
        frame = FakeFrame(640, 480)
        navigations: list[str] = []
        recorded: list[dict[str, object]] = []
        leaderboard = SimpleNamespace(
            record_score=lambda **kwargs: recorded.append(kwargs) or SimpleNamespace(rank=len(recorded)),
            complete_session=lambda *a, **k: None,
        )
        service = FakeAIJobService()
        state = SimpleNamespace(reveal_rows=[], reveal_replay_image=None)
        manager = SimpleNamespace(
            camera_service=SimpleNamespace(snapshot=lambda: SimpleNamespace(display_bgr=frame)),
            leaderboard_service=leaderboard,
            ai_job_service=service,
            state=state,
            go_to=lambda name, **k: navigations.append(name),
        )
        screen = MogMirrorScreen(manager)
        screen.session_id = "session-finish"
        screen.started_at_ms = 0
        screen.lanes = [
            MirrorLane(name="Mina", zone="p1", face=_mog_face(), live_score_samples=[80, 82]),
            MirrorLane(name="Theo", zone="p2", face=_mog_face(offset=0.1), live_score_samples=[60, 62]),
        ]

        screen._finish_round()

        # the full both-sides frame is stashed for the optional reveal replay
        self.assertIs(state.reveal_replay_image, frame)
        # no AI generation happens at finish — it's opt-in on the reveal screen
        self.assertEqual(service.submitted, [])
        self.assertTrue(all(row["ai_job_ids"] == [] for row in state.reveal_rows))
        self.assertEqual(len(state.reveal_rows), 2)
        self.assertEqual(navigations, ["score_reveal"])


class ReplayPromptTests(unittest.TestCase):
    def test_replay_prompt_names_winner_and_loser_scores(self) -> None:
        rows = [
            {"display_name": "Mina", "score": 90, "label": "MIRROR VERIFIED", "winner": True},
            {"display_name": "Theo", "score": 70, "label": "FLASH READY", "winner": False},
        ]

        prompt = build_replay_prompt(rows)

        self.assertIn("Mina", prompt)
        self.assertIn("90", prompt)
        self.assertIn("Theo", prompt)
        self.assertIn("70", prompt)

    def test_replay_prompt_handles_tie(self) -> None:
        rows = [
            {"display_name": "Mina", "score": 80, "winner": True},
            {"display_name": "Theo", "score": 80, "winner": True},
        ]

        self.assertIn("tie", build_replay_prompt(rows).lower())


def _mog_face(offset: float = 0.0, center_x: float = 0.25, center_y: float = 0.38, width: float = 0.26) -> dict[str, object]:
    return {
        "confidence": 1.0,
        "center": {"x": center_x, "y": center_y},
        "bbox": {"x": 0.12, "y": 0.18, "width": width, "height": 0.36},
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
