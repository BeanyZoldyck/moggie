from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.config import MoggieConfig

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SocialPostResult:
    platform: str
    status: str
    post_id: str | None = None
    url: str | None = None
    error: str | None = None


class SocialPostService:
    def __init__(
        self,
        *,
        enabled: bool,
        default_platform: str,
        x_api_key: str,
        x_api_key_secret: str,
        x_access_token: str,
        x_access_token_secret: str,
    ) -> None:
        self.enabled = enabled
        self.default_platform = default_platform.strip().lower() or "x"
        self.x_api_key = x_api_key.strip()
        self.x_api_key_secret = x_api_key_secret.strip()
        self.x_access_token = x_access_token.strip()
        self.x_access_token_secret = x_access_token_secret.strip()

    @classmethod
    def from_config(cls, config: MoggieConfig) -> "SocialPostService":
        return cls(
            enabled=config.enable_social_posting,
            default_platform=config.default_post_platform,
            x_api_key=config.x_api_key,
            x_api_key_secret=config.x_api_key_secret,
            x_access_token=config.x_access_token,
            x_access_token_secret=config.x_access_token_secret,
        )

    @property
    def x_ready(self) -> bool:
        return all(
            (
                self.x_api_key,
                self.x_api_key_secret,
                self.x_access_token,
                self.x_access_token_secret,
            )
        )

    def compose_caption(
        self,
        *,
        game_type: str,
        recap_url: str,
        winners: list[dict[str, Any]],
    ) -> str:
        winner_names = [str(row.get("display_name", "")).strip() for row in winners if row.get("winner")]
        winner_part = ", ".join(name for name in winner_names if name) or "Moggie players"
        return f"{winner_part} just took {game_type.replace('_', ' ')} at Moggie. {recap_url}"

    def post_to_x(self, *, recap_url: str, caption: str | None = None) -> SocialPostResult:
        if not self.enabled:
            return SocialPostResult(platform="x", status="disabled", error="Social posting disabled")
        if not self.x_ready:
            return SocialPostResult(platform="x", status="failed", error="Missing X credentials")
        text = (caption or "").strip()
        if not text:
            text = f"Arcade replay: {recap_url}"
        elif recap_url not in text:
            text = f"{text} {recap_url}"
        try:
            post_id = self._post_x_tweet(text)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("X post failed: %s", exc)
            return SocialPostResult(platform="x", status="failed", error=str(exc))
        return SocialPostResult(
            platform="x",
            status="posted",
            post_id=post_id,
            url=f"https://x.com/i/web/status/{post_id}",
        )

    def _post_x_tweet(self, text: str) -> str:
        from requests_oauthlib import OAuth1Session

        session = OAuth1Session(
            self.x_api_key,
            client_secret=self.x_api_key_secret,
            resource_owner_key=self.x_access_token,
            resource_owner_secret=self.x_access_token_secret,
        )
        response = session.post(
            "https://api.x.com/2/tweets",
            json={"text": text},
            timeout=20,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"X API HTTP {response.status_code}: {response.text}")
        payload = response.json()
        post_id = str(payload.get("data", {}).get("id") or "")
        if not post_id:
            raise RuntimeError(f"X API did not return tweet id: {payload}")
        return post_id
