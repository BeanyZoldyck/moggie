from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.app_event import current_time_ms
from app.cv.sixty_seven_counter import SixtySevenCounter
from app.ui import theme
from app.ui.render_utils import FontSet, build_fonts, draw_bottom_rule, draw_panel, draw_shadowed_text, draw_text, scaled_asset_image
from app.ui.renderers.camera_preview_renderer import CameraPreviewRenderer
from app.ui.renderers.hand_overlay_renderer import HandOverlayRenderer
from app.ui.sparkle_layer import SparkleLayer, ensure_sparkle_layer


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
    last_score: int = 0


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
        self.sparkles: SparkleLayer | None = None

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
                    extend_threshold=config.sixty_seven_extend_threshold,
                    return_threshold=config.sixty_seven_return_threshold,
                    min_delta=config.sixty_seven_min_swing,
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
        self.manager.speak_voiceline("sixty_seven", "intro")

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
                lane.counter.score_rate = max(lane.counter.score_rate, 750.0)

    def handle_app_event(self, event: Any) -> None:
        return None

    def update(self, now_ms: int, dt_ms: int) -> None:
        if self.started_at_ms is None:
            self.started_at_ms = now_ms
        if self.sparkles is not None:
            self.sparkles.update(dt_ms)
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
            before = lane.counter.display_score
            lane.counter.update_from_hands(
                zone_hands,
                now_ms=event_now_ms,
                frame_timestamp_ms=frame_timestamp_ms,
                require_both_hands=self.manager.config.sixty_seven_require_both_hands,
            )
            lane.counter.tick(dt_ms, active=True)
            if lane.counter.display_score > before:
                lane.pulse_until_ms = now_ms + 280
            lane.last_reps = lane.counter.reps
            lane.last_score = lane.counter.display_score

        if elapsed_ms >= self.countdown_ms + self.manager.config.sixty_seven_round_seconds * 1000:
            self._finish_round()

    def render(self, surface: Any) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        fonts = self.fonts
        width, height = surface.get_size()
        self.sparkles = ensure_sparkle_layer(pygame, self.sparkles, width, height)
        bg = scaled_asset_image(pygame, "sixseven_bg.PNG", (width, height))
        if bg is not None:
            surface.blit(bg, (0, 0))
        else:
            surface.fill(theme.BACKGROUND)
        
        camera_rect = pygame.Rect(90, 135, 1100, 330)
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
            split_pane=True,
        )
        state = self.manager.cv_service.latest_state() if self.manager.cv_service is not None else None
        hands = list(state.hand_landmarks.get("hands", [])) if state is not None else []
        stale = any(lane.counter.stale for lane in self.lanes)
        effect_rect = camera_rect.inflate(-6, -6)
        now_ms = pygame.time.get_ticks()
        self._render_tracking_fx(pygame, surface, effect_rect, now_ms)
        self.hand_renderer.render(
            surface,
            effect_rect,
            hands,
            stale=stale,
            split_x=self.manager.config.zone_split_x,
            point_mapper=self.preview_renderer.point_to_screen,
            show_trails=False,
        )

        panel_y = height - 174
        lane_w = (width - 108 - 24 * (len(self.lanes) - 1)) // len(self.lanes)
        for index, lane in enumerate(self.lanes):
            if index == 0:
                rect = pygame.Rect(172, height - 210, 220, 80)
            else:
                rect = pygame.Rect(width - 390, height - 210, 220, 80)
            color = theme.PLAYER_COLORS[index % len(theme.PLAYER_COLORS)]
            draw_shadowed_text(
                surface,
                lane.name,
                fonts.body,
                color,
                (rect.centerx, rect.top - 18),
                max_width=rect.width + 64,
            )
            self._draw_score(pygame, surface, rect, lane, fonts)

        if self._countdown_label():
            draw_text(surface, self._countdown_label(), fonts.masthead, theme.WARNING, (width // 2, height // 2), anchor="center")

        draw_text(
            surface,
            self._clock_label(),
            fonts.body,
            theme.WARNING,
            (width // 2, 520),
            anchor="center",
        )

        draw_bottom_rule(pygame, surface, height - 44, width)
        draw_text(surface, "SPACE STARTS / ESC HOME", fonts.small, theme.TEXT_MUTED, (42, height - 32))
        self.sparkles.render(surface)

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

    def _render_tracking_fx(self, pygame: Any, surface: Any, rect: Any, now_ms: int) -> None:
        divider_x = rect.left + int(rect.width * self.manager.config.zone_split_x)

        for lane in self.lanes:
            heat = self._speed_heat(lane)
            if heat <= 0.04:
                continue
            zone_rect = (
                pygame.Rect(rect.left, rect.top, max(1, divider_x - rect.left), rect.height)
                if lane.zone == "p1"
                else pygame.Rect(divider_x, rect.top, max(1, rect.right - divider_x), rect.height)
            )
            color = self._heat_color(heat)
            bar_w = int(zone_rect.width * min(1.0, heat))
            bar_y = zone_rect.top + 10
            if lane.zone == "p1":
                pygame.draw.rect(surface, color, pygame.Rect(zone_rect.left + 12, bar_y, bar_w, 4))
            else:
                pygame.draw.rect(surface, color, pygame.Rect(zone_rect.right - 12 - bar_w, bar_y, bar_w, 4))
            for offset in (0, 18, 36):
                phase_x = int((now_ms // 8 + offset) % max(1, zone_rect.width))
                x = zone_rect.left + phase_x if lane.zone == "p1" else zone_rect.right - phase_x
                pygame.draw.line(surface, (80, 60, 54), (x, zone_rect.top + 22), (x - 26 if lane.zone == "p1" else x + 26, zone_rect.top + 34), 1)

    def _draw_score(self, pygame: Any, surface: Any, rect: Any, lane: PlayerLane, fonts: FontSet) -> None:
        heat = self._speed_heat(lane)
        color = self._heat_color(heat)
        text = str(lane.counter.display_score)
        image = fonts.title.render(text, True, color)
        scale = 1.0 + heat * 0.36
        pulse = 1.0 + (0.06 if lane.pulse_until_ms > pygame.time.get_ticks() else 0.0)
        scale *= pulse
        max_width = max(80, rect.width - 190)
        scaled_width = int(image.get_width() * scale)
        scaled_height = int(image.get_height() * scale)
        if scaled_width > max_width:
            fit = max_width / max(1, scaled_width)
            scaled_width = int(scaled_width * fit)
            scaled_height = int(scaled_height * fit)
        if scaled_width != image.get_width() or scaled_height != image.get_height():
            image = pygame.transform.smoothscale(image, (max(1, scaled_width), max(1, scaled_height)))
        score_rect = image.get_rect(center=rect.center)
        shadow = image.copy()
        shadow.fill((42, 14, 16), special_flags=pygame.BLEND_RGB_MULT)
        surface.blit(shadow, score_rect.move(3, 3))
        surface.blit(image, score_rect)

        rate = int(lane.counter.score_rate)
        if rate > 20:
            label = f"+{rate}/s"
            draw_text(surface, label, fonts.small, color, (score_rect.right, score_rect.top - 16), anchor="topright")

    def _speed_heat(self, lane: PlayerLane | None) -> float:
        if lane is None:
            return 0.0
        return max(0.0, min(1.0, lane.counter.score_rate / 1_050.0))

    def _heat_color(self, heat: float) -> tuple[int, int, int]:
        heat = max(0.0, min(1.0, heat))
        if heat < 0.45:
            blend = heat / 0.45
            return (
                int(theme.TEXT[0] + (theme.WARNING[0] - theme.TEXT[0]) * blend),
                int(theme.TEXT[1] + (theme.WARNING[1] - theme.TEXT[1]) * blend),
                int(theme.TEXT[2] + (theme.WARNING[2] - theme.TEXT[2]) * blend),
            )
        blend = (heat - 0.45) / 0.55
        return (
            int(theme.WARNING[0] + (theme.ERROR[0] - theme.WARNING[0]) * blend),
            int(theme.WARNING[1] + (theme.ERROR[1] - theme.WARNING[1]) * blend),
            int(theme.WARNING[2] + (theme.ERROR[2] - theme.WARNING[2]) * blend),
        )

    def _finish_round(self) -> None:
        if self.finished or self.session_id is None:
            return
        self.finished = True
        # Stash the end-of-round frame for the optional opt-in recap on score reveal.
        camera_service = getattr(self.manager, "camera_service", None)
        frame = camera_service.latest_display_frame() if camera_service is not None else None
        self.manager.state.reveal_replay_image = frame
        rows = []
        high_score = max((lane.counter.display_score for lane in self.lanes), default=0)
        for lane in self.lanes:
            score_value = lane.counter.display_score
            label = self._label_for_score(score_value, winner=score_value == high_score)
            score = self.manager.leaderboard_service.record_score(
                session_id=self.session_id,
                player_display_name=lane.name,
                game_type="sixty_seven",
                score=score_value,
                label=label,
                metadata={"mode": self.manager.config.sixty_seven_mode, "zone": lane.zone},
            )
            rows.append(
                {
                    "display_name": lane.name,
                    "score": score_value,
                    "label": label,
                    "rank": score.rank,
                    "winner": score_value == high_score,
                    "ai_job_ids": [],
                }
            )
        self.manager.leaderboard_service.complete_session(
            self.session_id,
            metadata={"scores": {lane.name: lane.counter.display_score for lane in self.lanes}},
        )
        self.manager.state.reveal_rows = rows
        self.manager.state.last_session_id = self.session_id
        self.manager.speak_voiceline("sixty_seven", "end")
        self.manager.go_to("score_reveal")

    def _label_for_score(self, reps: int, *, winner: bool) -> str:
        if reps == 0:
            return "NO AURA DETECTED"
        if winner and reps >= 10_000:
            return "67 OVERLOAD"
        if winner and reps >= 5_000:
            return "67 CERTIFIED"
        if winner:
            return "67 CERTIFIED"
        if reps >= 3_500:
            return "CLEAN REPS"
        return "WARMUP ENERGY"
