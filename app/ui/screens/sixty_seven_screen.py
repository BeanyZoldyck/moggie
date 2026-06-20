from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.app_event import current_time_ms
from app.cv.sixty_seven_counter import SixtySevenCounter
from app.ui import theme
from app.ui.render_utils import FontSet, build_fonts, draw_bottom_rule, draw_panel, draw_text
from app.ui.renderers.camera_preview_renderer import CameraPreviewRenderer
from app.ui.renderers.hand_overlay_renderer import HandOverlayRenderer


def _pygame() -> Any:
    import pygame

    return pygame


@dataclass
class PlayerLane:
    name: str
    zone: str
    counter: SixtySevenCounter
    pulse_until_ms: int = 0
    last_reps: int = 0


class SixtySevenScreen:
    name = "sixty_seven"
    countdown_ms = 3_000

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.fonts: FontSet | None = None
        self.preview_renderer = CameraPreviewRenderer()
        self.hand_renderer = HandOverlayRenderer()
        self.lanes: list[PlayerLane] = []
        self.session_id: str | None = None
        self.started_at_ms: int | None = None
        self.finished = False

    def on_enter(self, **_: Any) -> None:
        config = self.manager.config
        names = self.manager.state.player_names or ["Player 1"]
        zones = ["p1"] if config.sixty_seven_mode == "solo" else ["p1", "p2"]
        self.lanes = [
            PlayerLane(
                name=names[index] if index < len(names) else f"Player {index + 1}",
                zone=zone,
                counter=SixtySevenCounter(
                    min_confidence=config.sixty_seven_min_confidence,
                    cooldown_ms=config.sixty_seven_rep_cooldown_ms,
                ),
            )
            for index, zone in enumerate(zones)
        ]
        session = self.manager.leaderboard_service.create_session(
            "sixty_seven",
            metadata={"mode": config.sixty_seven_mode},
        )
        self.session_id = session.id
        self.started_at_ms = None
        self.finished = False

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.manager.go_to("home")
        elif event.key in {pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER} and self.started_at_ms is None:
            self.started_at_ms = pygame.time.get_ticks()
        elif event.key == pygame.K_r:
            for lane in self.lanes:
                lane.counter.update(0.1, now_ms=pygame.time.get_ticks() - 500)
                lane.counter.update(0.55, now_ms=pygame.time.get_ticks() - 250)
                lane.counter.update(0.12, now_ms=pygame.time.get_ticks())

    def handle_app_event(self, event: Any) -> None:
        return None

    def update(self, now_ms: int, dt_ms: int) -> None:
        if self.started_at_ms is None:
            self.started_at_ms = now_ms
        if self.finished:
            return

        elapsed_ms = now_ms - self.started_at_ms
        if elapsed_ms < self.countdown_ms:
            return

        state = self.manager.cv_service.latest_state() if self.manager.cv_service is not None else None
        hands = []
        frame_timestamp_ms = None
        if state is not None:
            hands = list(state.hand_landmarks.get("hands", []))
            frame_timestamp_ms = state.timestamp_ms

        event_now_ms = current_time_ms()
        for lane in self.lanes:
            zone_hands = [hand for hand in hands if hand.get("zone") == lane.zone]
            before = lane.counter.reps
            lane.counter.update_from_hands(
                zone_hands,
                now_ms=event_now_ms,
                frame_timestamp_ms=frame_timestamp_ms,
                require_both_hands=self.manager.config.sixty_seven_require_both_hands,
            )
            if lane.counter.reps > before:
                lane.pulse_until_ms = now_ms + 280
            lane.last_reps = lane.counter.reps

        if elapsed_ms >= self.countdown_ms + self.manager.config.sixty_seven_round_seconds * 1000:
            self._finish_round()

    def render(self, surface: Any) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        fonts = self.fonts
        width, height = surface.get_size()
        surface.fill(theme.BACKGROUND)

        pygame.draw.rect(surface, (31, 24, 24), pygame.Rect(0, 0, width, 104))
        pygame.draw.rect(surface, theme.WARNING, pygame.Rect(0, 104, width, 4))
        draw_text(surface, "67 CHALLENGE", fonts.title, theme.TEXT, (42, 22), max_width=width - 360)
        draw_text(surface, self._clock_label(), fonts.card_title, theme.WARNING, (width - 48, 34), anchor="topright")

        camera_rect = pygame.Rect(42, 132, width - 84, max(260, height - 332))
        frame = self.manager.camera_service.latest_display_frame() if self.manager.camera_service is not None else None
        diagnostic = (
            self.manager.camera_service.diagnostic_message
            if self.manager.camera_service is not None
            else "Camera service is not configured."
        )
        self.preview_renderer.render(
            surface,
            camera_rect,
            frame_bgr=frame,
            diagnostic=diagnostic,
            show_divider=self.manager.config.show_zone_divider,
        )
        state = self.manager.cv_service.latest_state() if self.manager.cv_service is not None else None
        hands = list(state.hand_landmarks.get("hands", [])) if state is not None else []
        stale = any(lane.counter.stale for lane in self.lanes)
        self.hand_renderer.render(
            surface,
            camera_rect.inflate(-6, -6),
            hands,
            stale=stale,
            split_x=self.manager.config.zone_split_x,
        )

        panel_y = height - 174
        lane_w = (width - 108 - 24 * (len(self.lanes) - 1)) // len(self.lanes)
        now_ms = pygame.time.get_ticks()
        for index, lane in enumerate(self.lanes):
            rect = pygame.Rect(42 + index * (lane_w + 24), panel_y, lane_w, 104)
            color = theme.PLAYER_COLORS[index % len(theme.PLAYER_COLORS)]
            fill = (52, 44, 29) if lane.pulse_until_ms > now_ms else theme.SURFACE
            draw_panel(pygame, surface, rect, fill=fill, border=color, width=2)
            draw_text(surface, lane.name, fonts.body, theme.TEXT, (rect.left + 24, rect.top + 18), max_width=rect.width - 160)
            draw_text(surface, lane.zone.upper(), fonts.small, color, (rect.left + 24, rect.bottom - 34))
            draw_text(surface, str(lane.counter.reps), fonts.title, theme.TEXT, (rect.right - 28, rect.centery), anchor="midright")

        if self._countdown_label():
            draw_text(surface, self._countdown_label(), fonts.masthead, theme.WARNING, (width // 2, height // 2), anchor="center")

        draw_bottom_rule(pygame, surface, height - 44, width)
        draw_text(surface, "SPACE STARTS / ESC HOME", fonts.small, theme.TEXT_MUTED, (42, height - 32))

    def _clock_label(self) -> str:
        if self.started_at_ms is None:
            return "READY"
        now = _pygame().time.get_ticks()
        elapsed_ms = now - self.started_at_ms
        if elapsed_ms < self.countdown_ms:
            return f"{max(1, (self.countdown_ms - elapsed_ms + 999) // 1000)}"
        remaining = self.manager.config.sixty_seven_round_seconds - int((elapsed_ms - self.countdown_ms) / 1000)
        return f"{max(0, remaining)}s"

    def _countdown_label(self) -> str | None:
        if self.started_at_ms is None:
            return "READY"
        elapsed_ms = _pygame().time.get_ticks() - self.started_at_ms
        if elapsed_ms >= self.countdown_ms:
            return None
        return str(max(1, (self.countdown_ms - elapsed_ms + 999) // 1000))

    def _finish_round(self) -> None:
        if self.finished or self.session_id is None:
            return
        self.finished = True
        rows = []
        high_score = max((lane.counter.reps for lane in self.lanes), default=0)
        for lane in self.lanes:
            label = self._label_for_score(lane.counter.reps, winner=lane.counter.reps == high_score)
            score = self.manager.leaderboard_service.record_score(
                session_id=self.session_id,
                player_display_name=lane.name,
                game_type="sixty_seven",
                score=lane.counter.reps,
                label=label,
                metadata={"mode": self.manager.config.sixty_seven_mode, "zone": lane.zone},
            )
            rows.append(
                {
                    "display_name": lane.name,
                    "score": lane.counter.reps,
                    "label": label,
                    "rank": score.rank,
                }
            )
        self.manager.leaderboard_service.complete_session(
            self.session_id,
            metadata={"scores": {lane.name: lane.counter.reps for lane in self.lanes}},
        )
        self.manager.state.reveal_rows = rows
        self.manager.go_to("score_reveal")

    def _label_for_score(self, reps: int, *, winner: bool) -> str:
        if reps == 0:
            return "NO AURA DETECTED"
        if winner:
            return "67 CERTIFIED"
        if reps >= 6:
            return "CLEAN REPS"
        return "WARMUP ENERGY"
