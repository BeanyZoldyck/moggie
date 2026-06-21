from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.core.app_event import EVENT_AI_JOB_UPDATE, AppEvent, ai_job_update_payload
from app.games.recap_prompts import build_recap_prompt
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


class FakeStorageService:
    def __init__(self) -> None:
        self.uploads: list[tuple[Path, str, str]] = []

    def upload_video(self, path: Path, game_type: str, session_id: str) -> dict[str, str]:
        self.uploads.append((path, game_type, session_id))
        key = f"moggie/{game_type}/{session_id}.mp4"
        return {
            "bucket": "moggie-videos",
            "region": "us-east-1",
            "key": key,
            "url": f"https://moggie-videos.s3.us-east-1.amazonaws.com/{key}",
        }


class FakeVoiceAgentService:
    def __init__(self) -> None:
        self.contexts: list[object] = []
        self.inputs: list[str] = []

    def begin_social_prompt(self, context: object, on_status: object) -> None:
        self.contexts.append(context)

    def submit_user_text(self, text: str) -> None:
        self.inputs.append(text)


def _make_screen(
    *,
    game_type: str = "mog_mirror",
    enable_pika: bool = True,
    image: object = None,
) -> ScoreRevealScreen:
    if image is None:
        image = FakeFrame(640, 480)
    rows = {
        "mog_mirror": [
            {"display_name": "Mina", "score": 90, "label": "MIRROR VERIFIED", "winner": True, "ai_job_ids": []},
            {"display_name": "Theo", "score": 70, "label": "FLASH READY", "winner": False, "ai_job_ids": []},
        ],
        "sixty_seven": [
            {"display_name": "Mina", "score": 42, "label": "67 CERTIFIED", "winner": True, "ai_job_ids": []},
            {"display_name": "Theo", "score": 31, "label": "67 CERTIFIED", "winner": False, "ai_job_ids": []},
        ],
        "emoji_face_match": [
            {"display_name": "Mina", "score": 600, "label": "MOJI FINAL BOSS", "winner": True, "ai_job_ids": []},
            {"display_name": "Theo", "score": 400, "label": "REACTION READY", "winner": False, "ai_job_ids": []},
        ],
    }.get(game_type, [])
    state = SimpleNamespace(
        selected_game_type=game_type,
        player_names=["Mina", "Theo"],
        reveal_rows=rows,
        reveal_replay_image=image,
        last_session_id="session-test",
    )
    manager = SimpleNamespace(
        config=SimpleNamespace(
            enable_pika=enable_pika,
            save_generated_media=False,
            enable_s3_video_storage=False,
            media_dir=Path("/tmp/moggie-media"),
        ),
        ai_job_service=FakeAIJobService(),
        state=state,
        storage_service=FakeStorageService(),
        leaderboard_service=SimpleNamespace(record_media_asset=lambda *args, **kwargs: "media-test"),
    )
    return ScoreRevealScreen(manager)


def _succeeded(job_id: str, game_type: str = "mog_mirror") -> AppEvent:
    return AppEvent.create(
        EVENT_AI_JOB_UPDATE,
        payload=ai_job_update_payload(
            job_id,
            "succeeded",
            kind=f"{game_type}.recap_video",
            result={"uri": "https://v3.fal.media/files/recap.mp4"},
        ),
    )


def _failed(job_id: str) -> AppEvent:
    return AppEvent.create(
        EVENT_AI_JOB_UPDATE,
        payload=ai_job_update_payload(job_id, "failed", kind="mog_mirror.recap_video", error="boom"),
    )


def _sync_download(url: str, on_ready: object, **_: object) -> None:
    # The download callback now passes (path, url) to the queue.
    on_ready(Path("/tmp/moggie_fake_recap.mp4"), url)  # type: ignore[operator]


class RecapPromptTests(unittest.TestCase):
    def test_mog_mirror_prompt_names_winner_and_loser(self) -> None:
        rows = [
            {"display_name": "Mina", "score": 90, "label": "MIRROR VERIFIED", "winner": True},
            {"display_name": "Theo", "score": 70, "winner": False},
        ]
        prompt = build_recap_prompt("mog_mirror", rows)
        self.assertIn("Mina", prompt)
        self.assertIn("90", prompt)
        self.assertIn("Theo", prompt)

    def test_sixty_seven_prompt_mentions_reps(self) -> None:
        rows = [{"display_name": "Mina", "score": 42, "winner": True, "label": "67 CERTIFIED"}]
        prompt = build_recap_prompt("sixty_seven", rows)
        self.assertIn("Mina", prompt)
        self.assertIn("42", prompt)
        self.assertIn("reps", prompt.lower())

    def test_emoji_prompt_mentions_points(self) -> None:
        rows = [{"display_name": "Mina", "score": 600, "winner": True, "label": "MOJI FINAL BOSS"}]
        prompt = build_recap_prompt("emoji_face_match", rows)
        self.assertIn("Mina", prompt)
        self.assertIn("600", prompt)


class ScoreRevealReplayTests(unittest.TestCase):
    def test_can_generate_requires_pika_and_image(self) -> None:
        self.assertTrue(_make_screen()._can_generate_replay())
        self.assertFalse(_make_screen(enable_pika=False)._can_generate_replay())

    def test_can_generate_works_for_all_games(self) -> None:
        for game_type in ("mog_mirror", "sixty_seven", "emoji_face_match"):
            with self.subTest(game_type=game_type):
                self.assertTrue(_make_screen(game_type=game_type)._can_generate_replay())

    def test_start_replay_submits_game_typed_kind(self) -> None:
        for game_type in ("mog_mirror", "sixty_seven", "emoji_face_match"):
            with self.subTest(game_type=game_type):
                screen = _make_screen(game_type=game_type)
                with patch("app.ui.screens.score_reveal_screen.encode_bgr_jpeg", return_value=b"jpeg"):
                    screen._start_replay()
                kind, payload = screen.manager.ai_job_service.submitted[0]
                self.assertEqual(kind, f"{game_type}.recap_video")
                self.assertEqual(payload["image_bytes"], b"jpeg")
                self.assertIn("negative_prompt", payload)
                self.assertEqual(screen.replay_phase, "generating")

    def test_mog_mirror_prompt_is_result_aware(self) -> None:
        screen = _make_screen(game_type="mog_mirror")
        with patch("app.ui.screens.score_reveal_screen.encode_bgr_jpeg", return_value=b"jpeg"):
            screen._start_replay()
        _, payload = screen.manager.ai_job_service.submitted[0]
        self.assertIn("Mina", payload["prompt"])

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
        self.assertFalse(screen.social_prompt_started)

    def test_t_key_starts_social_prompt_when_replay_ready(self) -> None:
        screen = _make_screen()
        voice_agent = FakeVoiceAgentService()
        screen.manager.voice_agent_service = voice_agent
        screen.manager.speak_text = lambda text: None
        fake_pygame = SimpleNamespace(
            K_t=116,
            K_g=103,
            K_x=120,
            K_y=121,
            K_n=110,
            K_ESCAPE=27,
            K_h=104,
            K_RETURN=13,
            K_KP_ENTER=1073741912,
            K_SPACE=32,
            K_l=108,
            KEYDOWN=2,
        )
        with patch("app.ui.screens.score_reveal_screen.encode_bgr_jpeg", return_value=b"jpeg"):
            screen._start_replay()
        with patch("app.ui.screens.score_reveal_screen.download_in_background", new=_sync_download), patch(
            "app.ui.screens.score_reveal_screen.LoopingVideoPlayer", new=FakePlayer
        ):
            screen.handle_app_event(_succeeded("job-1"))
            screen.update(0, 0)
        with patch("app.ui.screens.score_reveal_screen._pygame", return_value=fake_pygame):
            screen.handle_event(SimpleNamespace(type=fake_pygame.KEYDOWN, key=fake_pygame.K_t))
        self.assertTrue(screen.social_prompt_started)
        self.assertEqual(len(voice_agent.contexts), 1)
        self.assertEqual(voice_agent.contexts[0].recap_url, "https://v3.fal.media/files/recap.mp4")

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

    def test_save_replay_uploads_to_s3_and_records_asset(self) -> None:
        screen = _make_screen()
        screen.manager.config.enable_s3_video_storage = True
        calls: list[tuple[object, ...]] = []
        screen.manager.leaderboard_service = SimpleNamespace(
            record_media_asset=lambda *args, **kwargs: calls.append((*args, kwargs))
        )

        saved = screen._save_replay(Path("/tmp/recap.mp4"), "https://fal.media/recap.mp4")

        self.assertIsNone(saved)
        self.assertEqual(len(screen.manager.storage_service.uploads), 1)
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0][:-1], calls[0][-1]
        self.assertEqual(args[2], "https://moggie-videos.s3.us-east-1.amazonaws.com/moggie/mog_mirror/session-test.mp4")
        self.assertEqual(kwargs["storage_mode"], "s3")


if __name__ == "__main__":
    unittest.main()
