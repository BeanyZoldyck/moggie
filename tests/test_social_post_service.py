from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.social_post_service import SocialPostService


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeOAuthSession:
    def __init__(self, *_: object, **__: object) -> None:
        self.posts: list[tuple[str, dict[str, object]]] = []

    def post(self, url: str, json: dict[str, object], timeout: int) -> _FakeResponse:  # noqa: A002
        self.posts.append((url, json))
        return _FakeResponse(201, {"data": {"id": "12345"}})


class SocialPostServiceTests(unittest.TestCase):
    def test_compose_caption_includes_game_and_url(self) -> None:
        service = SocialPostService(
            enabled=True,
            default_platform="x",
            x_api_key="k",
            x_api_key_secret="ks",
            x_access_token="t",
            x_access_token_secret="ts",
        )
        caption = service.compose_caption(
            game_type="mog_mirror",
            recap_url="https://cdn.example/video.mp4",
            winners=[{"display_name": "Mina", "winner": True}],
        )
        self.assertIn("Mina", caption)
        self.assertIn("mog mirror", caption)
        self.assertIn("https://cdn.example/video.mp4", caption)

    def test_post_to_x_returns_url_when_successful(self) -> None:
        service = SocialPostService(
            enabled=True,
            default_platform="x",
            x_api_key="k",
            x_api_key_secret="ks",
            x_access_token="t",
            x_access_token_secret="ts",
        )
        with patch("requests_oauthlib.OAuth1Session", _FakeOAuthSession):
            result = service.post_to_x(recap_url="https://cdn.example/video.mp4", caption="Replay drop")
        self.assertEqual(result.status, "posted")
        self.assertEqual(result.post_id, "12345")
        self.assertEqual(result.url, "https://x.com/i/web/status/12345")

    def test_post_to_x_fails_without_credentials(self) -> None:
        service = SocialPostService(
            enabled=True,
            default_platform="x",
            x_api_key="",
            x_api_key_secret="",
            x_access_token="",
            x_access_token_secret="",
        )
        result = service.post_to_x(recap_url="https://cdn.example/video.mp4", caption=None)
        self.assertEqual(result.status, "failed")
        self.assertIn("Missing X credentials", result.error or "")


if __name__ == "__main__":
    unittest.main()
