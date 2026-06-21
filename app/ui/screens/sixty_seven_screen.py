from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.core.app_event import current_time_ms
from app.cv.sixty_seven_counter import SixtySevenCounter
from app.ui import theme
from app.ui.render_utils import FontSet, build_fonts, draw_bottom_rule, draw_panel, draw_text, scaled_asset_image
from app.ui.renderers.camera_preview_renderer import CameraPreviewRenderer
from app.util.images import encode_bgr_jpeg


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
        bg = scaled_asset_image(pygame, "sixseven_bg.PNG", (width, height))
        if bg is not None:
            surface.blit(bg, (0, 0))
        else:
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
            split_pane=True,
        )
        state = self.manager.cv_service.latest_state() if self.manager.cv_service is not None else None
        hands = list(state.hand_landmarks.get("hands", [])) if state is not None else []
        stale = any(lane.counter.stale for lane in self.lanes)
        effect_rect = camera_rect.inflate(-6, -6)
        now_ms = pygame.time.get_ticks()
        self._render_tracking_fx(pygame, surface, effect_rect, hands, now_ms, stale=stale)

        panel_y = height - 174
        lane_w = (width - 108 - 24 * (len(self.lanes) - 1)) // len(self.lanes)
        for index, lane in enumerate(self.lanes):
            rect = pygame.Rect(42 + index * (lane_w + 24), panel_y, lane_w, 104)
            color = theme.PLAYER_COLORS[index % len(theme.PLAYER_COLORS)]
            fill = (52, 44, 29) if lane.pulse_until_ms > now_ms else theme.SURFACE
            draw_panel(pygame, surface, rect, fill=fill, border=color, width=2)
            draw_text(surface, lane.name, fonts.body, theme.TEXT, (rect.left + 24, rect.top + 18), max_width=rect.width - 160)
            draw_text(surface, lane.zone.upper(), fonts.small, color, (rect.left + 24, rect.bottom - 34))
            self._draw_score(pygame, surface, rect, lane, fonts)

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

    def _render_tracking_fx(
        self,
        pygame: Any,
        surface: Any,
        rect: Any,
        hands: list[dict[str, Any]],
        now_ms: int,
        *,
        stale: bool = False,
    ) -> None:
        lane_by_zone = {lane.zone: lane for lane in self.lanes}

        if stale:
            pygame.draw.rect(surface, (74, 40, 46), rect, 4)
            draw_text(surface, "STALE TRACKING", self.fonts.small, theme.ERROR, (rect.left + 16, rect.bottom - 34))
        elif not hands:
            draw_text(surface, "SHOW HANDS", self.fonts.small, (80, 176, 100), rect.center, anchor="center")

        for hand_index, hand in enumerate(hands[:8]):
            zone = str(hand.get("zone", ""))
            lane = lane_by_zone.get(zone)
            heat = max(0.18, self._speed_heat(lane) if lane is not None else 0.0)
            color = self._heat_color(heat)
            points = self._hand_orb_points(hand)
            screen_points = [
                (role, self.preview_renderer.point_to_screen(point, zone=zone, fallback_rect=rect))
                for role, point in points
            ]
            screen_points = [(role, point) for role, point in screen_points if point is not None]
            if not screen_points:
                continue

            for point_index, (role, point) in enumerate(screen_points):
                pulse = 0.5 + 0.5 * math.sin(now_ms * 0.012 + point_index * 0.9 + hand_index * 1.6)
                is_palm = role == "palm"
                is_tip = role == "tip"
                radius = 4 + int(pulse * 2 + heat * 3)
                if is_palm:
                    radius += 5
                elif is_tip:
                    radius += 3
                halo = radius + 4 + int(heat * 6)
                glow = self._dim_color(color, 0.42 if is_palm or is_tip else 0.30)
                pygame.draw.circle(surface, glow, point, halo, 2)
                pygame.draw.circle(surface, (28, 18, 22), point, radius + 2)
                pygame.draw.circle(surface, color, point, radius)
                if is_palm or is_tip:
                    pygame.draw.circle(surface, theme.TEXT, point, max(2, radius // 3))

                if role != "fill":
                    for spark_index in range(2):
                        angle = now_ms * 0.007 + point_index * 1.31 + spark_index * math.pi
                        distance = radius + 7 + spark_index * 5
                        spark = (
                            int(point[0] + math.cos(angle) * distance),
                            int(point[1] + math.sin(angle) * distance),
                        )
                        pygame.draw.circle(surface, self._dim_color(color, 0.65), spark, 2 + spark_index)

            palm = hand.get("palm_center")
            if isinstance(palm, dict):
                center = self.preview_renderer.point_to_screen(palm, zone=zone, fallback_rect=rect)
                if center is not None:
                    ring = 20 + int(heat * 26 + (now_ms // 90 + hand_index * 5) % 9)
                    pygame.draw.circle(surface, self._dim_color(color, 0.55), center, ring, 2)

    def _hand_orb_points(self, hand: dict[str, Any]) -> list[tuple[str, dict[str, float]]]:
        points: list[tuple[str, dict[str, float]]] = []
        palm = hand.get("palm_center")
        if isinstance(palm, dict):
            points.append(("palm", {"x": float(palm["x"]), "y": float(palm["y"])}))

        landmarks = hand.get("landmarks")
        if isinstance(landmarks, list):
            tip_indices = {4, 8, 12, 16, 20}
            for index, point in enumerate(landmarks):
                if not isinstance(point, dict):
                    continue
                role = "tip" if index in tip_indices else "landmark"
                points.append((role, {"x": float(point["x"]), "y": float(point["y"])}))

        bbox = hand.get("bbox")
        if isinstance(bbox, dict) and len(points) < 12:
            x = float(bbox.get("x", 0.0))
            y = float(bbox.get("y", 0.0))
            width = float(bbox.get("width", 0.0))
            height = float(bbox.get("height", 0.0))
            if width > 0.0 and height > 0.0:
                center_x = x + width * 0.5
                center_y = y + height * 0.5
                for step in range(14):
                    angle = step / 14.0 * math.tau
                    points.append(
                        (
                            "fill",
                            {
                                "x": center_x + math.cos(angle) * width * 0.34,
                                "y": center_y + math.sin(angle) * height * 0.36,
                            },
                        )
                    )
                for x_ratio in (0.24, 0.38, 0.50, 0.62, 0.76):
                    points.append(("tip", {"x": x + width * x_ratio, "y": y + height * 0.08}))
        return points

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
        score_rect = image.get_rect(midright=(rect.right - 28, rect.centery))
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

    def _dim_color(self, color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
        return (
            max(0, min(255, int(color[0] * factor))),
            max(0, min(255, int(color[1] * factor))),
            max(0, min(255, int(color[2] * factor))),
        )

    def _finish_round(self) -> None:
        if self.finished or self.session_id is None:
            return
        self.finished = True
        ai_job_ids = self._submit_replay_ai_job()
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
                metadata={"mode": self.manager.config.sixty_seven_mode, "zone": lane.zone, "ai_job_ids": ai_job_ids},
            )
            rows.append(
                {
                    "display_name": lane.name,
                    "score": score_value,
                    "label": label,
                    "rank": score.rank,
                    "ai_job_ids": ai_job_ids,
                }
            )
        self.manager.leaderboard_service.complete_session(
            self.session_id,
            metadata={"scores": {lane.name: lane.counter.display_score for lane in self.lanes}, "ai_job_ids": ai_job_ids},
        )
        self.manager.state.reveal_rows = rows
        self.manager.go_to("score_reveal")

    def _submit_replay_ai_job(self) -> list[str]:
        if not self.manager.config.enable_pika:
            return []
        service = getattr(self.manager, "ai_job_service", None)
        camera_service = getattr(self.manager, "camera_service", None)
        if service is None or camera_service is None:
            return []
        image_bytes = encode_bgr_jpeg(camera_service.latest_display_frame())
        if not image_bytes:
            return []
        scores = ", ".join(f"{lane.name}: {lane.counter.display_score}" for lane in self.lanes)
        prompt = (
            "Generate a viral replay clip for a chaotic arcade 67 Challenge battle. "
            f"Use the players in the image as the source. Final scores: {scores}. "
            "Make it feel like a high-energy sports replay with exaggerated motion, crowd hype, "
            "speed ramps, impact flashes, and a funny winner moment."
        )
        return [
            service.submit(
                "sixty_seven.viral_replay_video",
                {
                    "game_type": "sixty_seven",
                    "scores": {lane.name: lane.counter.display_score for lane in self.lanes},
                    "image_bytes": image_bytes,
                    "image_mime_type": "image/jpeg",
                    "prompt": prompt,
                },
            )
        ]

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
