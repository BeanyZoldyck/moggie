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
from app.ui.render_utils import FontSet, build_fonts, draw_bottom_rule, draw_panel, draw_text
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
    target_progress = 0.72

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
        surface.fill(theme.BACKGROUND)

        pygame.draw.rect(surface, (31, 24, 28), pygame.Rect(0, 0, width, 104))
        pygame.draw.rect(surface, (255, 96, 116), pygame.Rect(0, 104, width, 4))
        draw_text(surface, "EMOJI FACE MATCH", fonts.title, theme.TEXT, (42, 22), max_width=width - 410)
        draw_text(surface, self._clock_label(), fonts.card_title, (255, 96, 116), (width - 48, 34), anchor="topright")

        top_h = max(232, int(height * 0.42))
        camera_rect = pygame.Rect(42, 132, width - 84, top_h)
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
            show_divider=self.manager.config.show_zone_divider and len(self.lanes) > 1,
        )
        self.face_renderer.render(
            surface,
            camera_rect.inflate(-6, -6),
            self._faces(),
            split_x=self.manager.config.zone_split_x,
        )

        lanes_rect = pygame.Rect(42, camera_rect.bottom + 20, width - 84, max(180, height - camera_rect.bottom - 88))
        lane_h = max(78, (lanes_rect.height - 16 * (len(self.lanes) - 1)) // max(1, len(self.lanes)))
        now_ms = pygame.time.get_ticks()
        for index, lane in enumerate(self.lanes):
            rect = pygame.Rect(lanes_rect.left, lanes_rect.top + index * (lane_h + 16), lanes_rect.width, lane_h)
            self._render_lane(pygame, surface, rect, lane, index, now_ms)

        countdown = self._countdown_label()
        if countdown is not None:
            draw_text(surface, countdown, fonts.masthead, (255, 96, 116), (width // 2, height // 2), anchor="center")

        draw_bottom_rule(pygame, surface, height - 44, width)
        help_text = "SPACE STARTS / ESC HOME"
        if not self._ready_to_start() and self.manager.config.allow_manual_start_override:
            help_text = "SPACE MANUAL START / ESC HOME"
        draw_text(surface, self.message, fonts.small, theme.TEXT_MUTED, (42, height - 32), max_width=width // 2)
        draw_text(surface, help_text, fonts.small, theme.TEXT_MUTED, (width - 42, height - 32), anchor="topright")

    def _render_lane(self, pygame: Any, surface: Any, rect: Any, lane: EmojiLane, index: int, now_ms: int) -> None:
        assert self.fonts is not None
        color = theme.PLAYER_COLORS[index % len(theme.PLAYER_COLORS)]
        active = lane in self._active_lanes(max(0, self._play_elapsed_ms(now_ms)))
        border = color if lane.face is not None or self.manual_override else theme.BORDER
        fill = (38, 28, 34) if active else theme.SURFACE
        draw_panel(pygame, surface, rect, fill=fill, border=border, width=2)
        draw_text(surface, lane.name, self.fonts.body, theme.TEXT, (rect.left + 22, rect.top + 14), max_width=rect.width // 3)
        draw_text(surface, f"{lane.zone.upper()} / STREAK {lane.streak}", self.fonts.small, color, (rect.left + 22, rect.bottom - 34))
        draw_text(surface, str(lane.score), self.fonts.card_title, theme.TEXT, (rect.right - 24, rect.centery), anchor="midright")

        track = pygame.Rect(rect.left + 245, rect.top + 18, max(260, rect.width - 410), rect.height - 36)
        pygame.draw.line(surface, theme.DIM_BORDER, (track.left, track.centery), (track.right, track.centery), 2)
        target_x = track.left + int(track.width * self.target_progress)
        pygame.draw.line(surface, (255, 96, 116), (target_x, track.top), (target_x, track.bottom), 4)
        draw_text(surface, "MATCH", self.fonts.small, (255, 96, 116), (target_x, track.top - 2), anchor="bottom")

        for target in lane.targets:
            progress = max(0.0, min(1.25, (now_ms - target.spawn_ms) / self.travel_ms))
            x = track.left + int(track.width * progress)
            glyph_rect = pygame.Rect(x - 24, track.centery - 24, 48, 48)
            pygame.draw.rect(surface, theme.SURFACE_DARK, glyph_rect, border_radius=8)
            pygame.draw.rect(surface, color if not target.scored else theme.TEXT_MUTED, glyph_rect, 2, border_radius=8)
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
            lane.attempts += 1
            lane.score += result.points
            if result.hit:
                lane.hits += 1
                lane.streak += 1
                lane.best_streak = max(lane.best_streak, lane.streak)
                lane.feedback = f"HIT {expression_label(result.detected)}"
            else:
                lane.streak = 0
                lane.feedback = f"MISS {expression_label(result.detected)}"
            lane.feedback_until_ms = now_ms + 750

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
        self.manager.go_to("score_reveal")
