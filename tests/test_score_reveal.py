from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.core.app_event import EVENT_AI_JOB_UPDATE, AppEvent, ai_job_update_payload
from app.ui.screens.score_reveal_screen import ScoreRevealScreen


class FakeFrame:
    def __init__(self, width: int, height: int) -> None:
        self.shape = (height, width, 3)


class FakePlayer:
    is_ready = True

    def __init__(self, path: object, **_: object) -> None:
        self.path = path
        self.closed = False

    def current_frame_bgr(self) -> FakeFrame:
        return FakeFrame(640, 480)

    def advance(self, now_ms: float) -> None:
        return None

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeAIJobService:
    submitted: list[tuple[str, dict[str, object]]] | None = None

    def __post_init__(self) -> None:
        self.submitted = []

    def submit(self, kind: str, payload: dict[str, object]) -> str:
        assert self.submitted is not None
        self.submitted.append((kind, payload))
        return f"job-{len(self.submitted)}"


def _make_screen(*, enable_pika: bool = True, image=FakeFrame(640, 480)) -> ScoreRevealScreen:
    rows = [
        {"display_name": "Mina", "score": 90, "label": "MIRROR VERIFIED", "winner": True, "ai_job_ids": []},
        {"display_name": "Theo", "score": 70, "label": "FLASH READY", "winner": False, "ai_job_ids": []},
    ]
    state = SimpleNamespace(
        selected_game_type="mog_mirror",
        player_names=["Mina", "Theo"],
        reveal_rows=rows,
        reveal_replay_image=image,
    )
    manager = SimpleNamespace(
        config=SimpleNamespace(enable_pika=enable_pika),
        ai_job_service=FakeAIJobService(),
        state=state,
    )
    return ScoreRevealScreen(manager)


def _succeeded(job_id: str) -> AppEvent:
    return AppEvent.create(
        EVENT_AI_JOB_UPDATE,
        payload=ai_job_update_payload(
            job_id,
            "succeeded",
            kind="mog_mirror.replay_video",
            result={"uri": "https://v3.fal.media/files/replay.mp4"},
        ),
    )


def _failed(job_id: str) -> AppEvent:
    return AppEvent.create(
        EVENT_AI_JOB_UPDATE,
        payload=ai_job_update_payload(job_id, "failed", kind="mog_mirror.replay_video", error="boom"),
    )


def _sync_download(url: str, on_ready: object, **_: object) -> None:
    on_ready(Path("/tmp/moggie_fake_replay.mp4"))  # type: ignore[operator]


class ScoreRevealReplayTests(unittest.TestCase):
    def test_can_generate_requires_pika_and_image(self) -> None:
        self.assertTrue(_make_screen()._can_generate_replay())
        self.assertFalse(_make_screen(enable_pika=False)._can_generate_replay())
        self.assertFalse(_make_screen(image=None)._can_generate_replay())

    def test_start_replay_submits_one_result_aware_job(self) -> None:
        screen = _make_screen()

        with patch("app.ui.screens.score_reveal_screen.encode_bgr_jpeg", return_value=b"jpeg"):
            screen._start_replay()

        submitted = screen.manager.ai_job_service.submitted
        self.assertEqual(len(submitted), 1)
        kind, payload = submitted[0]
        self.assertEqual(kind, "mog_mirror.replay_video")
        self.assertEqual(payload["image_bytes"], b"jpeg")
        self.assertIn("negative_prompt", payload)
        self.assertIn("Mina", payload["prompt"])  # result-aware prompt
        self.assertEqual(screen.replay_phase, "generating")
        self.assertEqual(screen.replay_job_id, "job-1")

    def test_succeeded_event_downloads_and_becomes_ready(self) -> None:
        screen = _make_screen()
        with patch("app.ui.screens.score_reveal_screen.encode_bgr_jpeg", return_value=b"jpeg"):
            screen._start_replay()

        with patch("app.ui.screens.score_reveal_screen.download_in_background", new=_sync_download), patch(
            "app.ui.screens.score_reveal_screen.LoopingVideoPlayer", new=FakePlayer
        ):
            screen.handle_app_event(_succeeded("job-1"))
            screen.update(0, 0)

        self.assertEqual(screen.replay_phase, "ready")
        self.assertIsInstance(screen.replay_player, FakePlayer)

    def test_failed_event_sets_failed_phase(self) -> None:
        screen = _make_screen()
        with patch("app.ui.screens.score_reveal_screen.encode_bgr_jpeg", return_value=b"jpeg"):
            screen._start_replay()

        screen.handle_app_event(_failed("job-1"))

        self.assertEqual(screen.replay_phase, "failed")
        self.assertIn("boom", screen.replay_error)

    def test_unrelated_job_event_does_not_change_replay_phase(self) -> None:
        screen = _make_screen()
        with patch("app.ui.screens.score_reveal_screen.encode_bgr_jpeg", return_value=b"jpeg"):
            screen._start_replay()

        screen.handle_app_event(_succeeded("some-other-job"))

        self.assertEqual(screen.replay_phase, "generating")


if __name__ == "__main__":
    unittest.main()
