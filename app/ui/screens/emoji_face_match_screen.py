from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.cv.expression_features import extract_expression_features
from app.games.emoji_face_match import (
    build_expression_sequence,
    evaluate_match,
    expression_glyph,
    expression_label,
    label_for_score,
)
from app.ui import theme
from app.ui.render_utils import FontSet, build_fonts, draw_bottom_rule, draw_panel, draw_text, scaled_asset_image
from app.ui.renderers.camera_preview_renderer import CameraPreviewRenderer
from app.ui.renderers.face_overlay_renderer import FaceOverlayRenderer


def _pygame() -> Any:
    import pygame

    return pygame


@dataclass
class EmojiTarget:
    expression: str
    spawn_ms: int
    scored: bool = False
    hit: bool | None = None


@dataclass
class EmojiLane:
    name: str
    zone: str
    sequence: list[str]
    face: dict[str, Any] | None = None
    targets: list[EmojiTarget] = field(default_factory=list)
    next_index: int = 0
    score: int = 0
    hits: int = 0
    attempts: int = 0
    streak: int = 0
    best_streak: int = 0
    feedback: str = "READY"
    feedback_until_ms: int = 0
    last_spawn_ms: int | None = None


class EmojiFaceMatchScreen:
    name = "emoji_face_match"
    countdown_ms = 3_000
    spawn_interval_ms = 1_700
    travel_ms = 3_000
    target_progress = 0.74

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.fonts: FontSet | None = None
        self.preview_renderer = CameraPreviewRenderer()
        self.face_renderer = FaceOverlayRenderer()
        self.lanes: list[EmojiLane] = []
        self.session_id: str | None = None
        self.started_at_ms: int | None = None
        self.finished = False
        self.message = "CENTER FACES IN THE LANES"
        self.manual_override = False
        self.emoji_images = {}

    def on_enter(self, **_: Any) -> None:
        config = self.manager.config
        names = self.manager.state.player_names or ["Player 1", "Player 2"]
        mode = config.emoji_mode
        zones = ["p1"] if mode == "solo" else ["p1", "p2"]
        target_count = max(4, int(config.emoji_round_seconds * 1000 / self.spawn_interval_ms) + 2)
        self.lanes = [
            EmojiLane(
                name=names[index] if index < len(names) else f"Player {index + 1}",
                zone=zone,
                sequence=build_expression_sequence(f"{mode}:{index}:{names[index] if index < len(names) else index}", target_count),
            )
            for index, zone in enumerate(zones)
        ]
        session = self.manager.leaderboard_service.create_session(
            "emoji_face_match",
            metadata={"mode": mode},
        )
        self.session_id = session.id
        self.started_at_ms = None
        self.finished = False
        self.message = self._ready_message()
        self.manual_override = False
        self.manager.speak_voiceline("emoji_face_match", "intro")

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.manager.go_to("home")
        elif event.key in {pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER}:
            if self._ready_to_start() or self.manager.config.allow_manual_start_override:
                self.manual_override = not self._ready_to_start()
                self.started_at_ms = pygame.time.get_ticks()
                self.message = "MATCH THE FACE IN THE TARGET"
            else:
                self.message = self._ready_message()

    def handle_app_event(self, event: Any) -> None:
        return None

    def update(self, now_ms: int, dt_ms: int) -> None:
        self._sync_faces()
        if self.finished:
            return
        if self.started_at_ms is None:
            return

        elapsed_ms = now_ms - self.started_at_ms
        if elapsed_ms < self.countdown_ms:
            return

        play_ms = elapsed_ms - self.countdown_ms
        active_lanes = self._active_lanes(play_ms)
        for lane in active_lanes:
            self._spawn_due_target(lane, now_ms)
        for lane in self.lanes:
            self._score_due_targets(lane, now_ms)
            lane.targets = [target for target in lane.targets if now_ms - target.spawn_ms <= self.travel_ms + 700]

        if play_ms >= self.manager.config.emoji_round_seconds * 1000:
            self._finish_round()

    def render(self, surface: Any) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        fonts = self.fonts
        width, height = surface.get_size()
        bg = scaled_asset_image(pygame, "emoji_bg.PNG", (width, height))
        if bg is not None:
            surface.blit(bg, (0, 0))
        else:
            surface.fill(theme.BACKGROUND)

        camera_rect = pygame.Rect(100, 115, 1080, 290)
        frame = self.manager.camera_service.latest_display_frame() if self.manager.camera_service is not None else None
        diagnostic = (
            self.manager.camera_service.diagnostic_message
            if self.manager.camera_service is not None
            else "Camera service is not configured."
        )
        preview_rect = self.preview_renderer.render(
            surface,
            camera_rect,
            frame_bgr=frame,
            diagnostic=diagnostic,
            show_divider=self.manager.config.show_zone_divider and len(self.lanes) > 1,
            split_pane=self.manager.config.show_zone_divider and len(self.lanes) > 1,
        )
        self.face_renderer.render(
            surface,
            preview_rect or camera_rect.inflate(-6, -6),
            self._faces(),
            split_x=self.manager.config.zone_split_x,
            point_mapper=self.preview_renderer.point_to_screen,
        )
        self._render_face_fx(pygame, surface, preview_rect or camera_rect.inflate(-6, -6), now_ms=pygame.time.get_ticks())

        lanes_rect = pygame.Rect(42, camera_rect.bottom + 20, width - 84, max(180, height - camera_rect.bottom - 88))
        lane_h = max(78, (lanes_rect.height - 16 * (len(self.lanes) - 1)) // max(1, len(self.lanes)))
        now_ms = pygame.time.get_ticks()
        for index, lane in enumerate(self.lanes):
            rect = pygame.Rect(lanes_rect.left, lanes_rect.top + index * (lane_h + 16), lanes_rect.width, lane_h)
            self._render_lane(pygame, surface, rect, lane, index, now_ms)

        countdown = self._countdown_label()
        if countdown is not None:
            draw_text(surface, countdown, fonts.masthead, theme.WARNING, (width // 2, height // 2 - 120), anchor="center")

        draw_bottom_rule(pygame, surface, height - 44, width)
        help_text = "SPACE STARTS / ESC HOME"
        if not self._ready_to_start() and self.manager.config.allow_manual_start_override:
            help_text = "SPACE MANUAL START / ESC HOME"
        draw_text(surface, self.message, fonts.small, theme.TEXT_MUTED, (42, height - 32), max_width=width // 2)
        draw_text(surface, help_text, fonts.small, theme.TEXT_MUTED, (width - 42, height - 32), anchor="topright")

    def _render_lane(self, pygame: Any, surface: Any, rect: Any, lane: EmojiLane, index: int, now_ms: int) -> None:
        assert self.fonts is not None
        if index == 0:
            color = (255, 60, 60)      # red for Player 1
        else:
            color = (0, 130, 255)      # blue for Player 2
        active = lane in self._active_lanes(max(0, self._play_elapsed_ms(now_ms)))
        border = color if lane.face is not None or self.manual_override else theme.BORDER
        fill = (38, 28, 34) if active else theme.SURFACE
        if lane.zone == "p2":
            streak_y = rect.bottom - 64
        else:
            streak_y = rect.bottom - 34

        draw_text(
            surface,
            f"STREAK {lane.streak}",
            self.fonts.small,
            color,
            (rect.centerx, streak_y),
            anchor="center",
        )
        self._draw_lane_score(pygame, surface, rect, lane, color, now_ms)

        track_y = rect.top + 25

        if lane.zone == "p2":
            track_y = rect.top - 10

        track = pygame.Rect(rect.left + 245, track_y, max(260, rect.width - 410), rect.height - 36)   

        pygame.draw.line(surface, theme.DIM_BORDER, (track.left, track.centery), (track.right, track.centery), 2)
        target_x = track.left + int(track.width * self.target_progress)

        self._render_target_gate_fx(pygame, surface, track, lane, color, now_ms)

        for target in lane.targets:
            progress = max(0.0, min(1.25, (now_ms - target.spawn_ms) / self.travel_ms))
            x = track.left + int(track.width * progress)
            glyph_rect = pygame.Rect(x - 24, track.centery - 24, 48, 48)
            trail_color = self._emoji_heat_color(lane, color)
            for trail_index in range(3):
                trail_x = x - 16 * (trail_index + 1)
                pygame.draw.line(surface, (72, 46, 58), (trail_x, track.centery), (x - 8, track.centery), 2)
            if target.scored and target.hit is not None:
                fx_color = theme.ACCENT if target.hit else theme.ERROR
                pygame.draw.circle(surface, fx_color, glyph_rect.center, 30 + int((now_ms // 80) % 8), 2)
                if not target.hit:
                    pygame.draw.line(surface, fx_color, glyph_rect.topleft, glyph_rect.bottomright, 3)
                    pygame.draw.line(surface, fx_color, glyph_rect.topright, glyph_rect.bottomleft, 3)

            emoji_filename = {
                "neutral": "neutral.png",
                "smile": "smile.png",
                "surprised": "surprised.png",
                "tongue_out": "tongue.png",
                "wink": "wink.png",
                "look_left": "left.png",
                "look_right": "right.png",
            }.get(target.expression)

            emoji_image = scaled_asset_image(pygame, emoji_filename, (48, 48)) if emoji_filename else None

            if emoji_image is not None:
                emoji_rect = emoji_image.get_rect(center=glyph_rect.center)
                surface.blit(emoji_image, emoji_rect)
            else:
                draw_text(surface, expression_glyph(target.expression), self.fonts.body, theme.TEXT, glyph_rect.center, anchor="center")
            feedback_color = theme.ACCENT if lane.feedback.startswith("HIT") else theme.TEXT_MUTED
            if lane.feedback_until_ms > now_ms:
                draw_text(surface, lane.feedback, self.fonts.small, feedback_color, (rect.right - 150, rect.bottom - 34), anchor="topright")

    def _sync_faces(self) -> None:
        faces = self._faces()
        faces_by_zone = {face.get("zone"): face for face in faces}
        mode = self.manager.config.emoji_mode
        for lane in self.lanes:
            if mode in {"solo", "alternating"} and faces:
                lane.face = faces[0]
            else:
                lane.face = faces_by_zone.get(lane.zone)
        if self.started_at_ms is None:
            self.message = "READY TO START" if self._ready_to_start() else self._ready_message()

    def _faces(self) -> list[dict[str, Any]]:
        state = self.manager.cv_service.latest_state() if self.manager.cv_service is not None else None
        if state is None:
            return []
        return list(state.face_landmarks.get("faces", []))

    def _ready_to_start(self) -> bool:
        if self.manager.config.emoji_mode == "versus":
            zones = {lane.zone for lane in self.lanes if lane.face is not None}
            return {"p1", "p2"} <= zones
        return any(lane.face is not None for lane in self.lanes)

    def _ready_message(self) -> str:
        if self.manager.config.emoji_mode == "versus":
            return "NEED ONE FACE IN EACH LANE"
        return "NEED ONE FACE TO START"

    def _active_lanes(self, play_ms: int) -> list[EmojiLane]:
        if self.manager.config.emoji_mode != "alternating" or len(self.lanes) < 2:
            return self.lanes
        turn_ms = max(self.spawn_interval_ms, self.travel_ms)
        active_index = (play_ms // turn_ms) % len(self.lanes)
        return [self.lanes[int(active_index)]]

    def _spawn_due_target(self, lane: EmojiLane, now_ms: int) -> None:
        if lane.next_index >= len(lane.sequence):
            return
        if lane.last_spawn_ms is not None and now_ms - lane.last_spawn_ms < self.spawn_interval_ms:
            return
        lane.targets.append(EmojiTarget(lane.sequence[lane.next_index], now_ms))
        lane.next_index += 1
        lane.last_spawn_ms = now_ms

    def _score_due_targets(self, lane: EmojiLane, now_ms: int) -> None:
        scoring_ms = int(self.travel_ms * self.target_progress)
        for target in lane.targets:
            if target.scored or now_ms - target.spawn_ms < scoring_ms:
                continue
            features = extract_expression_features(lane.face)
            result = evaluate_match(target.expression, features)
            target.scored = True
            target.hit = result.hit
            lane.attempts += 1
            lane.score += result.points
            if result.hit:
                lane.hits += 1
                lane.streak += 1
                lane.best_streak = max(lane.best_streak, lane.streak)
                lane.feedback = f"HIT {expression_label(result.target)}"
            else:
                lane.streak = 0
                lane.feedback = f"MISS {expression_label(result.target)}"
            lane.feedback_until_ms = now_ms + 750

    def _render_face_fx(self, pygame: Any, surface: Any, rect: Any, *, now_ms: int) -> None:
        for lane in self.lanes:
            if lane.face is None:
                continue
            center = lane.face.get("center") if isinstance(lane.face.get("center"), dict) else None
            if center is None:
                continue
            point = self.preview_renderer.point_to_screen(center, zone=lane.zone, fallback_rect=rect)
            if point is None:
                continue
            heat = self._lane_heat(lane)
            color = self._emoji_heat_color(lane, theme.PLAYER_COLORS[0] if lane.zone == "p1" else theme.PLAYER_COLORS[1])
            radius = int(24 + heat * 28 + (now_ms // 90) % 8)
            pygame.draw.circle(surface, color, point, radius, 2)
            pygame.draw.line(surface, (82, 52, 64), (point[0] - radius - 14, point[1]), (point[0] - radius // 2, point[1]), 2)
            pygame.draw.line(surface, (82, 52, 64), (point[0] + radius // 2, point[1]), (point[0] + radius + 14, point[1]), 2)

    def _render_target_gate_fx(self, pygame: Any, surface: Any, track: Any, lane: EmojiLane, color: tuple[int, int, int], now_ms: int) -> None:
        heat = self._lane_heat(lane)
        gate_x = track.left + int(track.width * self.target_progress)
        gate_color = self._emoji_heat_color(lane, color)
        if heat > 0.05:
            pulse = int(heat * 22 + (now_ms // 60) % 6)
            pygame.draw.rect(surface, gate_color, pygame.Rect(gate_x - 5 - pulse // 4, track.top - 4, 10 + pulse // 2, track.height + 8), 2, border_radius=4)
        for offset in (0, 22, 44):
            x = track.left + int((now_ms // 9 + offset) % max(1, track.width))
            pygame.draw.line(surface, (76, 48, 62), (x, track.bottom + 3), (x + 20, track.bottom + 11), 1)

    def _draw_lane_score(self, pygame: Any, surface: Any, rect: Any, lane: EmojiLane, color: tuple[int, int, int], now_ms: int) -> None:
        heat = self._lane_heat(lane)
        score_color = self._emoji_heat_color(lane, color)
        image = self.fonts.card_title.render(str(lane.score), True, score_color)
        pulse = 0.12 if lane.feedback_until_ms > now_ms and lane.feedback.startswith("HIT") else 0.0
        scale = 1.0 + min(0.34, lane.streak * 0.035) + pulse
        size = (max(1, int(image.get_width() * scale)), max(1, int(image.get_height() * scale)))
        max_width = max(70, rect.width - 580)
        if size[0] > max_width:
            fit = max_width / size[0]
            size = (max(1, int(size[0] * fit)), max(1, int(size[1] * fit)))
        if size != image.get_size():
            image = pygame.transform.smoothscale(image, size)
        if lane.zone == "p2":
            score_rect = image.get_rect(midright=(rect.right - 72, rect.centery - 34))
        else:
            score_rect = image.get_rect(midright=(rect.right - 72, rect.centery))
        surface.blit(image, score_rect)
        if lane.streak >= 2:
            draw_text(surface, f"x{lane.streak}", self.fonts.small, score_color, (score_rect.right, score_rect.top - 14), anchor="topright")

    def _lane_heat(self, lane: EmojiLane) -> float:
        feedback_heat = 0.45 if lane.feedback_until_ms > _pygame().time.get_ticks() else 0.0
        return max(0.0, min(1.0, lane.streak * 0.16 + feedback_heat))

    def _emoji_heat_color(self, lane: EmojiLane, base: tuple[int, int, int]) -> tuple[int, int, int]:
        heat = self._lane_heat(lane)
        target = theme.ACCENT if not lane.feedback.startswith("MISS") else theme.ERROR
        if heat > 0.65:
            target = theme.WARNING if not lane.feedback.startswith("MISS") else theme.ERROR
        return (
            int(base[0] + (target[0] - base[0]) * heat),
            int(base[1] + (target[1] - base[1]) * heat),
            int(base[2] + (target[2] - base[2]) * heat),
        )

    def _clock_label(self) -> str:
        if self.started_at_ms is None:
            return self.manager.config.emoji_mode.upper()
        elapsed_ms = _pygame().time.get_ticks() - self.started_at_ms
        if elapsed_ms < self.countdown_ms:
            return str(max(1, (self.countdown_ms - elapsed_ms + 999) // 1000))
        remaining = self.manager.config.emoji_round_seconds - int((elapsed_ms - self.countdown_ms) / 1000)
        return f"{max(0, remaining)}s"

    def _countdown_label(self) -> str | None:
        if self.started_at_ms is None:
            return None
        elapsed_ms = _pygame().time.get_ticks() - self.started_at_ms
        if elapsed_ms >= self.countdown_ms:
            return None
        return str(max(1, (self.countdown_ms - elapsed_ms + 999) // 1000))

    def _play_elapsed_ms(self, now_ms: int) -> int:
        if self.started_at_ms is None:
            return 0
        return max(0, now_ms - self.started_at_ms - self.countdown_ms)

    def _finish_round(self) -> None:
        if self.finished or self.session_id is None:
            return
        self.finished = True
        # Stash the end-of-round frame for the optional opt-in recap on score reveal.
        camera_service = getattr(self.manager, "camera_service", None)
        frame = camera_service.latest_display_frame() if camera_service is not None else None
        self.manager.state.reveal_replay_image = frame
        high_score = max((lane.score for lane in self.lanes), default=0)
        rows = []
        for lane in self.lanes:
            winner = lane.score == high_score
            label = label_for_score(lane.score, winner=winner, hits=lane.hits, attempts=lane.attempts)
            score_record = self.manager.leaderboard_service.record_score(
                session_id=self.session_id,
                player_display_name=lane.name,
                game_type="emoji_face_match",
                score=lane.score,
                label=label,
                metadata={
                    "mode": self.manager.config.emoji_mode,
                    "zone": lane.zone,
                    "hits": lane.hits,
                    "attempts": lane.attempts,
                    "best_streak": lane.best_streak,
                    "manual_override": self.manual_override,
                },
            )
            rows.append(
                {
                    "display_name": lane.name,
                    "score": lane.score,
                    "label": label,
                    "rank": score_record.rank,
                    "winner": winner,
                    "ai_job_ids": [],
                }
            )
        self.manager.leaderboard_service.complete_session(
            self.session_id,
            metadata={
                "mode": self.manager.config.emoji_mode,
                "scores": {lane.name: lane.score for lane in self.lanes},
                "hits": {lane.name: lane.hits for lane in self.lanes},
            },
        )
        self.manager.state.reveal_rows = rows
        self.manager.state.last_session_id = self.session_id
        self.manager.speak_voiceline("emoji_face_match", "end")
        self.manager.go_to("score_reveal")
