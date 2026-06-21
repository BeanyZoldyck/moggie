from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import MoggieConfig
from app.core.app_event import AppEvent
from app.core.game_catalog import GAMES
from app.services.camera_service import CameraService
from app.services.cv_service import CVService
from app.services.ai_job_service import AIJobService
from app.services.leaderboard_service import LeaderboardService


class Screen(Protocol):
    name: str

    def on_enter(self, **kwargs: Any) -> None:
        ...

    def handle_event(self, event: Any) -> None:
        ...

    def handle_app_event(self, event: AppEvent) -> None:
        ...

    def update(self, now_ms: int, dt_ms: int) -> None:
        ...

    def render(self, surface: Any) -> None:
        ...


@dataclass
class ScreenState:
    selected_game_type: str = GAMES[0].game_type
    player_names: list[str] = field(default_factory=list)
    reveal_rows: list[dict[str, Any]] = field(default_factory=list)
    # Full camera frame from the last round (both sides), for the opt-in recap video.
    reveal_replay_image: Any = None
    # Session ID of the last completed round — used by score reveal to record media assets.
    last_session_id: str | None = None


class ScreenManager:
    def __init__(
        self,
        config: MoggieConfig,
        leaderboard_service: LeaderboardService,
        *,
        camera_service: CameraService | None = None,
        cv_service: CVService | None = None,
        ai_job_service: AIJobService | None = None,
        initial_screen: str = "home",
    ) -> None:
        from app.ui.screens.home_screen import HomeScreen
        from app.ui.screens.emoji_face_match_screen import EmojiFaceMatchScreen
        from app.ui.screens.idle_attract_screen import IdleAttractScreen
        from app.ui.screens.leaderboard_screen import LeaderboardScreen
        from app.ui.screens.mog_mirror_screen import MogMirrorScreen
        from app.ui.screens.player_setup_screen import PlayerSetupScreen
        from app.ui.screens.score_reveal_screen import ScoreRevealScreen
        from app.ui.screens.sixty_seven_screen import SixtySevenScreen

        self.config = config
        self.leaderboard_service = leaderboard_service
        self.camera_service = camera_service
        self.cv_service = cv_service
        self.ai_job_service = ai_job_service
        self.state = ScreenState()
        self.should_quit = False
        self.last_input_ms = 0
        self._screens: dict[str, Screen] = {
            "home": HomeScreen(self),
            "idle_attract": IdleAttractScreen(self),
            "player_setup": PlayerSetupScreen(self),
            "emoji_face_match": EmojiFaceMatchScreen(self),
            "mog_mirror": MogMirrorScreen(self),
            "sixty_seven": SixtySevenScreen(self),
            "score_reveal": ScoreRevealScreen(self),
            "leaderboard": LeaderboardScreen(self),
        }
        if initial_screen not in self._screens:
            raise ValueError(f"Unknown screen: {initial_screen}")
        self.current_screen = initial_screen
        self._screens[self.current_screen].on_enter()

    @property
    def active(self) -> Screen:
        return self._screens[self.current_screen]

    def go_to(self, screen_name: str, **kwargs: Any) -> None:
        if screen_name not in self._screens:
            raise ValueError(f"Unknown screen: {screen_name}")
        self.current_screen = screen_name
        self._screens[screen_name].on_enter(**kwargs)

    def request_quit(self) -> None:
        self.should_quit = True

    def handle_event(self, event: Any) -> None:
        self.last_input_ms = self._event_ticks()
        self.active.handle_event(event)

    def handle_app_event(self, event: AppEvent) -> None:
        handler = getattr(self.active, "handle_app_event", None)
        if handler is not None:
            handler(event)

    def update(self, now_ms: int, dt_ms: int) -> None:
        if self.last_input_ms == 0:
            self.last_input_ms = now_ms
        if (
            self.config.idle_attract_enabled
            and self.current_screen == "home"
            and now_ms - self.last_input_ms >= self.config.idle_timeout_seconds * 1000
        ):
            self.go_to("idle_attract")
        self.active.update(now_ms, dt_ms)

    def render(self, surface: Any) -> None:
        self.active.render(surface)

    def wake_to_home(self) -> None:
        self.last_input_ms = self._event_ticks()
        self.go_to("home")

    def _event_ticks(self) -> int:
        try:
            import pygame

            return pygame.time.get_ticks()
        except Exception:
            return 0
