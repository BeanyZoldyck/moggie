from __future__ import annotations

import queue
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.app_event import EVENT_AI_JOB_UPDATE, AppEvent
from app.cv.zone_assignment import assign_face
from app.games.mog_mirror import (
    MOG_AVATAR_NEGATIVE_PROMPT,
    MOG_AVATAR_PROMPT,
    crop_upper_body,
    label_for_aura,
    score_aura,
)
from app.ui import theme
from app.ui.render_utils import FontSet, build_fonts, draw_bottom_rule, draw_panel, draw_text, scaled_asset_image
from app.ui.renderers.camera_preview_renderer import CameraPreviewRenderer
from app.ui.renderers.face_overlay_renderer import FaceOverlayRenderer
from app.util.images import encode_bgr_jpeg
from app.util.video_playback import LoopingVideoPlayer, download_in_background

# Round phases.
PHASE_READY = "ready"
PHASE_GENERATING = "generating"
PHASE_SCORING = "scoring"


def _pygame() -> Any:
    import pygame

    return pygame


@dataclass
class MirrorLane:
    name: str
    zone: str
    face: dict[str, Any] | None = None
    live_score: int | None = None
    live_score_updated_at_ms: int | None = None
    live_score_samples: list[int] = field(default_factory=list)
    display_score: float = 0.0
    display_score_target: float = 0.0
    display_score_rate: float = 0.0
    display_pulse_until_ms: int = 0


class MogMirrorScreen:
    name = "mog_mirror"
    live_score_duration_ms = 10_000
    live_score_update_interval_ms = 500
    countdown_ms = live_score_duration_ms

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.fonts: FontSet | None = None
        self.preview_renderer = CameraPreviewRenderer()
        self.face_renderer = FaceOverlayRenderer()
        self.lanes: list[MirrorLane] = []
        self.session_id: str | None = None
        self.started_at_ms: int | None = None
        self.finished = False
        self.message = "CENTER BOTH FACES IN THEIR LANES"
        self.manual_override = False
        # --- Mog Avatar mode state ---
        self.phase = PHASE_READY
        self.avatar_jobs: dict[str, str] = {}
        self.avatar_status: dict[str, str] = {}
        self.avatar_players: dict[str, LoopingVideoPlayer] = {}
        self.avatar_paths: dict[str, Path] = {}
        self.photo_faces: dict[str, dict[str, Any] | None] = {}
        self.lane_crops: dict[str, Any] = {}
        self.avatar_fallback = False
        self.generation_deadline_ms: int | None = None
        self._download_queue: "queue.Queue[tuple[str, Path | None]]" = queue.Queue()
        self._video_face_detector: Any | None = None

    def on_enter(self, **_: Any) -> None:
        names = self.manager.state.player_names or ["Player 1", "Player 2"]
        self.lanes = [
            MirrorLane(name=names[0] if len(names) > 0 else "Player 1", zone="p1"),
            MirrorLane(name=names[1] if len(names) > 1 else "Player 2", zone="p2"),
        ]
        session = self.manager.leaderboard_service.create_session(
            "mog_mirror",
            metadata={"mode": "versus"},
        )
        self.session_id = session.id
        self.started_at_ms = None
        self.finished = False
        self.message = "CENTER BOTH FACES IN THEIR LANES"
        self.manual_override = False
        self._entered_at_ms: int | None = None
        self._reset_avatar_state()

    def _reset_avatar_state(self) -> None:
        self._close_players()
        self.phase = PHASE_READY
        self.avatar_jobs = {}
        self.avatar_status = {}
        self.avatar_players = {}
        self.avatar_paths = {}
        self.photo_faces = {}
        self.lane_crops = {}
        self.avatar_fallback = False
        self.generation_deadline_ms = None
        self._download_queue = queue.Queue()

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.manager.go_to("home")
        elif event.key in {pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER}:
            if self.phase != PHASE_READY:
                return
            if self._entered_at_ms is not None and pygame.time.get_ticks() - self._entered_at_ms < 300:
                return
            if self._ready_to_capture() or self.manager.config.allow_manual_start_override:
                self.manual_override = not self._ready_to_capture()
                if self._avatar_mode_enabled():
                    self._capture_and_request_avatars()
                else:
                    self.started_at_ms = pygame.time.get_ticks()
                    self.phase = PHASE_SCORING
                    self.message = "HOLD THAT ENERGY"
            else:
                self.message = "NEED ONE FACE IN EACH LANE"

    def handle_app_event(self, event: AppEvent) -> None:
        if event.type != EVENT_AI_JOB_UPDATE or self.phase != PHASE_GENERATING:
            return
        job_id = event.payload.get("job_id")
        if not isinstance(job_id, str):
            return
        zone = self._zone_for_job(job_id)
        if zone is None:
            return
        status = event.payload.get("status")
        if status == "succeeded":
            result = (event.payload.get("metadata") or {}).get("result") or {}
            url = result.get("uri") or result.get("video_url")
            if isinstance(url, str) and url:
                self._begin_avatar_download(zone, url)
            else:
                self.avatar_status[zone] = "failed"
        elif status in {"failed", "timed_out"}:
            self.avatar_status[zone] = "failed"

    def update(self, now_ms: int, dt_ms: int) -> None:
        if self._entered_at_ms is None:
            self._entered_at_ms = now_ms
        if self.phase == PHASE_READY:
            self._sync_faces()
            return
        if self.phase == PHASE_GENERATING:
            self._update_generating(now_ms)
            return
        # PHASE_SCORING
        if self.finished:
            return
        if self.started_at_ms is None:
            return
        self._update_scoring_faces(now_ms)
        self._update_live_scores(now_ms)
        self._tick_display_scores(now_ms, dt_ms)
        if now_ms - self.started_at_ms >= self.live_score_duration_ms:
            self._finish_round()

    def render(self, surface: Any) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        fonts = self.fonts
        width, height = surface.get_size()
        bg = scaled_asset_image(pygame, "mog_mirror_bg.png", (width, height))
        if bg is not None:
            surface.blit(bg, (0, 0))
        else:
            surface.fill(theme.BACKGROUND)

        pygame.draw.rect(surface, (24, 31, 24), pygame.Rect(0, 0, width, 104))
        pygame.draw.rect(surface, theme.ACCENT, pygame.Rect(0, 104, width, 4))
        draw_text(surface, "MOG MIRROR", fonts.title, theme.TEXT, (42, 22), max_width=width - 360)
        draw_text(surface, self._clock_label(), fonts.card_title, theme.ACCENT, (width - 48, 34), anchor="topright")

        camera_rect = pygame.Rect(42, 132, width - 84, max(260, height - 328))
        frame = self._frame_to_show()
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
            show_divider=self.manager.config.show_zone_divider,
            split_pane=self.manager.config.show_zone_divider,
        )
        faces = self._faces_for_overlay()
        self.face_renderer.render(
            surface,
            preview_rect or camera_rect.inflate(-6, -6),
            faces,
            split_x=self.manager.config.zone_split_x,
            point_mapper=self.preview_renderer.point_to_screen,
        )
        self._render_mirror_fx(pygame, surface, preview_rect or camera_rect.inflate(-6, -6), faces, pygame.time.get_ticks())

        panel_y = height - 170
        lane_w = (width - 108 - 24) // 2
        now_ms = pygame.time.get_ticks()
        for index, lane in enumerate(self.lanes):
            rect = pygame.Rect(42 + index * (lane_w + 24), panel_y, lane_w, 100)
            color = theme.PLAYER_COLORS[index % len(theme.PLAYER_COLORS)]
            detected = lane.face is not None
            draw_panel(pygame, surface, rect, fill=theme.SURFACE, border=color if detected else theme.BORDER, width=2)
            draw_text(surface, lane.name, fonts.body, theme.TEXT, (rect.left + 24, rect.top + 18), max_width=rect.width - 190)
            draw_text(surface, lane.zone.upper(), fonts.small, color, (rect.left + 24, rect.bottom - 32))
            status = "FACE LOCK" if detected else "REPOSITION"
            if self.started_at_ms is None:
                draw_text(surface, status, fonts.body, color if detected else theme.TEXT_MUTED, (rect.right - 24, rect.centery), anchor="midright")
            else:
                draw_text(surface, "MOG SCORE", fonts.small, theme.TEXT_MUTED, (rect.right - 24, rect.top + 18), anchor="topright")
                self._draw_live_score(pygame, surface, rect, lane, color, now_ms)

        countdown = self._countdown_label()
        if countdown is not None:
            draw_text(surface, countdown, fonts.masthead, theme.ACCENT, (width // 2, height // 2), anchor="center")

        draw_bottom_rule(pygame, surface, height - 44, width)
        help_text = "SPACE CAPTURES / ESC HOME"
        if not self._ready_to_capture() and self.manager.config.allow_manual_start_override:
            help_text = "SPACE MANUAL CAPTURE / ESC HOME"
        draw_text(surface, self.message, fonts.small, theme.TEXT_MUTED, (42, height - 32), max_width=width // 2)
        draw_text(surface, help_text, fonts.small, theme.TEXT_MUTED, (width - 42, height - 32), anchor="topright")

        if self.phase == PHASE_GENERATING:
            self._render_generating_overlay(surface, width, height)

    # ------------------------------------------------------------------
    # Avatar mode
    # ------------------------------------------------------------------
    def _avatar_mode_enabled(self) -> bool:
        config = getattr(self.manager, "config", None)
        service = getattr(self.manager, "ai_job_service", None)
        return bool(config is not None and getattr(config, "enable_pika", False) and service is not None)

    def _capture_and_request_avatars(self) -> None:
        pygame = _pygame()
        service = self.manager.ai_job_service
        snapshot = self.manager.camera_service.snapshot() if self.manager.camera_service is not None else None
        frame = snapshot.display_bgr if snapshot is not None else None
        if frame is None and self.manager.camera_service is not None:
            frame = self.manager.camera_service.latest_display_frame()
        submitted_any = False
        for lane in self.lanes:
            self.photo_faces[lane.zone] = lane.face
            crop = crop_upper_body(frame, lane.face, lane.zone)
            self.lane_crops[lane.zone] = crop
            image_bytes = encode_bgr_jpeg(crop)
            if not image_bytes:
                self.avatar_status[lane.zone] = "failed"
                continue
            payload = {
                "game_type": "mog_mirror",
                "display_name": lane.name,
                "zone": lane.zone,
                "image_bytes": image_bytes,
                "image_mime_type": "image/jpeg",
                "prompt": MOG_AVATAR_PROMPT,
                "negative_prompt": MOG_AVATAR_NEGATIVE_PROMPT,
                "has_crop": crop is not None,
            }
            job_id = service.submit("mog_mirror.avatar_video", payload)
            self.avatar_jobs[lane.zone] = job_id
            self.avatar_status[lane.zone] = "generating"
            submitted_any = True

        now_ms = pygame.time.get_ticks()
        if not submitted_any:
            self._enter_fallback_scoring(now_ms)
            return
        timeout_seconds = int(getattr(self.manager.config, "ai_timeout_seconds", 60))
        # Avatar jobs run sequentially through the single AI worker, so budget per lane.
        self.generation_deadline_ms = now_ms + (timeout_seconds * max(1, len(self.lanes)) + 15) * 1000
        self.phase = PHASE_GENERATING
        self.message = "LOADING MOG AVATAR"

    def _zone_for_job(self, job_id: str) -> str | None:
        for zone, candidate in self.avatar_jobs.items():
            if candidate == job_id:
                return zone
        return None

    def _begin_avatar_download(self, zone: str, url: str) -> None:
        if self.avatar_status.get(zone) in {"downloading", "ready"}:
            return
        self.avatar_status[zone] = "downloading"
        download_in_background(url, lambda path, z=zone: self._download_queue.put((z, path)))

    def _update_generating(self, now_ms: int) -> None:
        self._drain_download_queue()
        zones = [lane.zone for lane in self.lanes]
        statuses = [self.avatar_status.get(zone) for zone in zones]
        if any(status == "failed" for status in statuses):
            self._enter_fallback_scoring(now_ms)
            return
        if self.generation_deadline_ms is not None and now_ms >= self.generation_deadline_ms:
            self._enter_fallback_scoring(now_ms)
            return
        ready = all(status == "ready" for status in statuses) and all(
            self.avatar_players.get(zone) is not None for zone in zones
        )
        if ready:
            self._enter_avatar_scoring(now_ms)

    def _drain_download_queue(self) -> None:
        while True:
            try:
                zone, path = self._download_queue.get_nowait()
            except queue.Empty:
                break
            if path is None:
                self.avatar_status[zone] = "failed"
                continue
            player = LoopingVideoPlayer(path)
            if not player.is_ready:
                player.close()
                self.avatar_status[zone] = "failed"
                continue
            self.avatar_players[zone] = player
            self.avatar_paths[zone] = path
            self.avatar_status[zone] = "ready"

    def _enter_avatar_scoring(self, now_ms: int) -> None:
        self.phase = PHASE_SCORING
        self.avatar_fallback = False
        self.started_at_ms = now_ms
        self.message = "HOLD THAT ENERGY"

    def _enter_fallback_scoring(self, now_ms: int) -> None:
        self._close_players()
        self.avatar_players = {}
        self.phase = PHASE_SCORING
        self.avatar_fallback = True
        self.started_at_ms = now_ms
        self.message = "CAMERA MODE — HOLD THAT ENERGY"

    def _avatar_scoring_active(self) -> bool:
        return self.phase == PHASE_SCORING and not self.avatar_fallback and bool(self.avatar_players)

    def _update_scoring_faces(self, now_ms: int) -> None:
        if not self._avatar_scoring_active():
            self._sync_faces()
            return
        for lane in self.lanes:
            player = self.avatar_players.get(lane.zone)
            if player is None:
                continue
            player.advance(now_ms)
            face = self._detect_video_face(player.current_frame_bgr(), lane.zone)
            if face is not None:
                lane.face = face
            elif self.photo_faces.get(lane.zone) is not None:
                lane.face = self.photo_faces[lane.zone]
            # else: keep last-known face

    def _detect_video_face(self, frame: Any, zone: str) -> dict[str, Any] | None:
        if frame is None:
            return None
        detector = self._video_face_detector
        if detector is None:
            # Screen-owned detector: mediapipe FaceMesh is not thread-safe, so we
            # must not share cv_service's instance (it runs on a worker thread).
            from app.cv.face_detection import FaceDetectionService

            detector = FaceDetectionService()
            self._video_face_detector = detector
        try:
            faces = detector.detect(frame)
        except Exception:  # noqa: BLE001 - a flaky generated frame must not crash the round
            return None
        if not faces:
            return None
        face = dict(faces[0])
        assign_face(face, split_x=self._zone_split_x())
        face["zone"] = zone
        return face

    def _zone_split_x(self) -> float:
        return float(getattr(self.manager.config, "zone_split_x", 0.5))

    def _frame_to_show(self) -> Any | None:
        camera = self.manager.camera_service.latest_display_frame() if self.manager.camera_service is not None else None
        if self._avatar_scoring_active():
            composite = self._avatar_composite_frame()
            if composite is not None:
                return composite
        return camera

    def _avatar_composite_frame(self) -> Any | None:
        frames = [self.avatar_players.get(lane.zone) for lane in self.lanes]
        current = [player.current_frame_bgr() if player is not None else None for player in frames]
        if any(frame is None for frame in current):
            return None
        try:
            import cv2
            import numpy as np
        except Exception:  # noqa: BLE001
            return None
        target_h = min(frame.shape[0] for frame in current)
        resized = []
        for frame in current:
            scale_w = int(frame.shape[1] * target_h / frame.shape[0])
            resized.append(cv2.resize(frame, (max(1, scale_w), target_h)))
        half_w = min(frame.shape[1] for frame in resized)
        cropped = [frame[:, :half_w] for frame in resized]
        return np.hstack(cropped)

    def _faces_for_overlay(self) -> list[dict[str, Any]]:
        if self._avatar_scoring_active():
            # The avatar video is its own visual; landmark boxes would be noisy and
            # mis-mapped against the composite, so we skip the overlay here.
            return []
        return self._faces()

    def _render_generating_overlay(self, surface: Any, width: int, height: int) -> None:
        pygame = _pygame()
        assert self.fonts is not None
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        surface.blit(overlay, (0, 0))
        dots = "." * (1 + (pygame.time.get_ticks() // 500) % 3)
        draw_text(surface, f"LOADING MOG AVATAR{dots}", self.fonts.masthead, theme.ACCENT, (width // 2, height // 2 - 40), anchor="center")
        draw_text(surface, self._avatar_status_line(), self.fonts.body, theme.TEXT, (width // 2, height // 2 + 28), anchor="center")

    def _avatar_status_line(self) -> str:
        labels = {
            "generating": "GENERATING",
            "downloading": "DOWNLOADING",
            "ready": "READY",
            "failed": "FAILED",
        }
        parts = [
            f"{lane.zone.upper()} {labels.get(self.avatar_status.get(lane.zone, 'generating'), 'GENERATING')}"
            for lane in self.lanes
        ]
        return "  ·  ".join(parts)

    def _close_players(self) -> None:
        for player in self.avatar_players.values():
            try:
                player.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Shared / camera logic
    # ------------------------------------------------------------------
    def _sync_faces(self) -> None:
        faces_by_zone = {face.get("zone"): face for face in self._faces()}
        for lane in self.lanes:
            lane.face = faces_by_zone.get(lane.zone)
        if self.started_at_ms is None:
            self.message = "READY TO CAPTURE" if self._ready_to_capture() else "CENTER BOTH FACES IN THEIR LANES"

    def _faces(self) -> list[dict[str, Any]]:
        state = self.manager.cv_service.latest_state() if self.manager.cv_service is not None else None
        if state is None:
            return []
        return list(state.face_landmarks.get("faces", []))

    def _ready_to_capture(self) -> bool:
        zones = {lane.zone for lane in self.lanes if lane.face is not None}
        return {"p1", "p2"} <= zones

    def _clock_label(self) -> str:
        if self.started_at_ms is None:
            return "READY"
        remaining = self.countdown_ms - (_pygame().time.get_ticks() - self.started_at_ms)
        return "SNAP" if remaining <= 0 else str(max(1, (remaining + 999) // 1000))

    def _countdown_label(self) -> str | None:
        if self.started_at_ms is None:
            return None
        remaining = self.countdown_ms - (_pygame().time.get_ticks() - self.started_at_ms)
        if remaining <= 0:
            return None
        return str(max(1, (remaining + 999) // 1000))

    def _update_live_scores(self, now_ms: int, *, force: bool = False) -> None:
        if self.session_id is None:
            return
        for lane in self.lanes:
            if (
                not force
                and lane.live_score_updated_at_ms is not None
                and now_ms - lane.live_score_updated_at_ms < self.live_score_update_interval_ms
            ):
                continue
            lane.live_score = score_aura(
                session_id=self.session_id,
                display_name=lane.name,
                zone=lane.zone,
                face=lane.face,
                manual_override=self.manual_override,
                sample_ms=now_ms - self.started_at_ms if self.started_at_ms is not None else now_ms,
            )
            lane.live_score_samples.append(lane.live_score)
            lane.live_score_updated_at_ms = now_ms
            self._set_display_target(lane, now_ms)

    def _set_display_target(self, lane: MirrorLane, now_ms: int) -> None:
        aura = 0 if lane.live_score is None else lane.live_score
        face_bonus = 850 if lane.face is not None else 0
        sample_bonus = min(900, len(lane.live_score_samples) * 55)
        target = min(9_999.0, max(0.0, (aura - 18) * 118.0 + face_bonus + sample_bonus))
        delta = abs(target - lane.display_score)
        lane.display_score_target = target
        lane.display_score_rate = max(lane.display_score_rate, min(2_700.0, 480.0 + delta * 3.2))
        lane.display_pulse_until_ms = now_ms + 340

    def _tick_display_scores(self, now_ms: int, dt_ms: int) -> None:
        del now_ms
        dt_seconds = max(0.0, min(0.1, dt_ms / 1000.0))
        for lane in self.lanes:
            diff = lane.display_score_target - lane.display_score
            if abs(diff) > 0.5:
                step = min(abs(diff), max(80.0, lane.display_score_rate) * dt_seconds)
                lane.display_score += step if diff > 0 else -step
            lane.display_score_rate *= 0.90 ** max(1.0, dt_ms / 16.667)
            if lane.display_score_rate < 20.0:
                lane.display_score_rate = 0.0

    def _render_mirror_fx(self, pygame: Any, surface: Any, rect: Any, faces: list[dict[str, Any]], now_ms: int) -> None:
        lane_by_zone = {lane.zone: lane for lane in self.lanes}
        for face in faces:
            bbox = face.get("bbox")
            if not isinstance(bbox, dict):
                continue
            zone = str(face.get("zone", ""))
            lane = lane_by_zone.get(zone)
            heat = self._lane_heat(lane)
            color = self._heat_color(heat, theme.PLAYER_COLORS[0] if zone == "p1" else theme.PLAYER_COLORS[1])
            top_left = self.preview_renderer.point_to_screen(
                {"x": float(bbox.get("x", 0.0)), "y": float(bbox.get("y", 0.0))},
                zone=zone,
                fallback_rect=rect,
            )
            bottom_right = self.preview_renderer.point_to_screen(
                {
                    "x": float(bbox.get("x", 0.0)) + float(bbox.get("width", 0.0)),
                    "y": float(bbox.get("y", 0.0)) + float(bbox.get("height", 0.0)),
                },
                zone=zone,
                fallback_rect=rect,
            )
            if top_left is None or bottom_right is None:
                continue
            box = pygame.Rect(
                min(top_left[0], bottom_right[0]),
                min(top_left[1], bottom_right[1]),
                max(8, abs(bottom_right[0] - top_left[0])),
                max(8, abs(bottom_right[1] - top_left[1])),
            )
            radius = int(8 + heat * 20)
            pygame.draw.rect(surface, color, box.inflate(radius, radius), 2, border_radius=8)
            pygame.draw.rect(surface, (54, 64, 48), box.inflate(radius + 10, radius + 10), 1, border_radius=10)
            scan_y = box.top + int((now_ms // 6) % max(1, box.height))
            pygame.draw.line(surface, color, (box.left - 16, scan_y), (box.right + 16, scan_y), 2)
            for index in range(3):
                offset = int((now_ms // 14 + index * 24) % max(1, box.width + 48))
                x = box.left - 24 + offset
                pygame.draw.line(surface, (72, 88, 65), (x, box.top - 14), (x + 20, box.top - 4), 1)

    def _draw_live_score(self, pygame: Any, surface: Any, rect: Any, lane: MirrorLane, color: tuple[int, int, int], now_ms: int) -> None:
        if lane.live_score is None:
            draw_text(surface, "--", self.fonts.card_title, color, (rect.right - 24, rect.bottom - 54), anchor="midright")
            return
        heat = self._lane_heat(lane)
        text_color = self._heat_color(heat, color)
        image = self.fonts.card_title.render(str(int(lane.display_score)), True, text_color)
        scale = 1.0 + heat * 0.28 + (0.08 if lane.display_pulse_until_ms > now_ms else 0.0)
        size = (max(1, int(image.get_width() * scale)), max(1, int(image.get_height() * scale)))
        max_width = max(80, rect.width - 210)
        if size[0] > max_width:
            fit = max_width / size[0]
            size = (max(1, int(size[0] * fit)), max(1, int(size[1] * fit)))
        if size != image.get_size():
            image = pygame.transform.smoothscale(image, size)
        score_rect = image.get_rect(midright=(rect.right - 24, rect.bottom - 54))
        shadow = image.copy()
        shadow.fill((12, 32, 16), special_flags=pygame.BLEND_RGB_MULT)
        surface.blit(shadow, score_rect.move(2, 2))
        surface.blit(image, score_rect)
        if lane.display_score_rate > 50:
            draw_text(surface, f"+{int(lane.display_score_rate)}/s", self.fonts.small, text_color, (score_rect.right, score_rect.top - 14), anchor="topright")

    def _lane_heat(self, lane: MirrorLane | None) -> float:
        if lane is None:
            return 0.0
        return max(0.0, min(1.0, lane.display_score_rate / 2_700.0))

    def _heat_color(self, heat: float, base: tuple[int, int, int]) -> tuple[int, int, int]:
        target = theme.ERROR if heat > 0.58 else theme.WARNING
        blend = heat if heat <= 0.58 else (heat - 0.58) / 0.42
        if heat <= 0.58:
            target = theme.WARNING
        return (
            int(base[0] + (target[0] - base[0]) * blend),
            int(base[1] + (target[1] - base[1]) * blend),
            int(base[2] + (target[2] - base[2]) * blend),
        )

    def _finish_round(self) -> None:
        if self.finished or self.session_id is None:
            return
        self.finished = True
        now_ms = self.started_at_ms + self.live_score_duration_ms if self.started_at_ms is not None else 0
        self._update_live_scores(now_ms, force=True)
        avatar_mode = self._avatar_scoring_active()
        camera_frame = None
        if not avatar_mode:
            snapshot = self.manager.camera_service.snapshot() if self.manager.camera_service is not None else None
            camera_frame = snapshot.display_bgr if snapshot is not None else None
        scored = []
        for lane in self.lanes:
            score = self._average_live_score(lane)
            if score is None:
                score = score_aura(
                    session_id=self.session_id,
                    display_name=lane.name,
                    zone=lane.zone,
                    face=lane.face,
                    manual_override=self.manual_override,
                )
            scored.append((lane, score))
        high_score = max(score for _, score in scored)

        rows = []
        for lane, score in scored:
            winner = score == high_score
            label = label_for_aura(score, winner=winner, face_detected=lane.face is not None)
            crop, ai_job_ids = self._reveal_media(lane, score, label, avatar_mode, camera_frame)
            score_record = self.manager.leaderboard_service.record_score(
                session_id=self.session_id,
                player_display_name=lane.name,
                game_type="mog_mirror",
                score=score,
                label=label,
                metadata={
                    "zone": lane.zone,
                    "face_detected": lane.face is not None,
                    "manual_override": self.manual_override,
                    "avatar_mode": avatar_mode,
                    "ai_job_ids": ai_job_ids,
                },
            )
            rows.append(
                {
                    "display_name": lane.name,
                    "score": score,
                    "label": label,
                    "rank": score_record.rank,
                    "winner": winner,
                    "crop_bgr": crop,
                    "ai_job_ids": ai_job_ids,
                }
            )
        self.manager.leaderboard_service.complete_session(
            self.session_id,
            metadata={"manual_override": self.manual_override, "scores": {row["display_name"]: row["score"] for row in rows}},
        )
        self.manager.state.reveal_rows = rows
        self._close_players()
        self.manager.go_to("score_reveal")

    def _reveal_media(
        self,
        lane: MirrorLane,
        score: int,
        label: str,
        avatar_mode: bool,
        camera_frame: Any | None,
    ) -> tuple[Any | None, list[str]]:
        if avatar_mode:
            player = self.avatar_players.get(lane.zone)
            frame = player.current_frame_bgr() if player is not None else None
            if frame is not None:
                crop = crop_upper_body(frame, lane.face, lane.zone)
            else:
                crop = self.lane_crops.get(lane.zone)
            # Avatar already generated at the start of the round; reuse its job id
            # for the reveal instead of spending a second generation.
            ai_job_ids = [self.avatar_jobs[lane.zone]] if lane.zone in self.avatar_jobs else []
            return crop, ai_job_ids
        crop = crop_upper_body(camera_frame, lane.face, lane.zone)
        return crop, self._submit_ai_jobs(lane, crop, score, label)

    def _average_live_score(self, lane: MirrorLane) -> int | None:
        if not lane.live_score_samples:
            return lane.live_score
        return round(sum(lane.live_score_samples) / len(lane.live_score_samples))

    def _submit_ai_jobs(self, lane: MirrorLane, crop: Any | None, score: int, label: str) -> list[str]:
        service = getattr(self.manager, "ai_job_service", None)
        if service is None:
            return []
        job_ids = []
        payload = {
            "game_type": "mog_mirror",
            "display_name": lane.name,
            "zone": lane.zone,
            "score": score,
            "label": label,
            "has_crop": crop is not None,
        }
        image_bytes = encode_bgr_jpeg(crop)
        if image_bytes:
            payload["image_bytes"] = image_bytes
            payload["image_mime_type"] = "image/jpeg"
        if self.manager.config.enable_pika:
            payload["prompt"] = (
                "Create a short, sensational arcade replay from this Mog Mirror portrait. "
                "Make it glossy, dramatic, funny, and score-reveal worthy."
            )
            job_ids.append(service.submit("mog_mirror.victory_video", payload))
            return job_ids
        if self.manager.config.enable_image_generation:
            job_ids.append(service.submit("mog_mirror.caricature", payload))
        return job_ids
