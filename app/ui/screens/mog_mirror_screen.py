from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.games.mog_mirror import crop_upper_body, label_for_aura, score_aura
from app.ui import theme
from app.ui.render_utils import FontSet, build_fonts, draw_bottom_rule, draw_panel, draw_text, scaled_asset_image
from app.ui.renderers.camera_preview_renderer import CameraPreviewRenderer
from app.ui.renderers.face_overlay_renderer import FaceOverlayRenderer
from app.ui.sparkle_layer import SparkleLayer


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
    display_target_index: int = -1
    last_face_center: tuple[float, float] | None = None
    last_face_box_area: float | None = None
    movement_energy: float = 0.0


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
        self._entered_at_ms: int | None = None
        self.sparkles = None

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
        self._entered_at_ms = None
        self.manager.speak_voiceline("mog_mirror", "intro")

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.manager.go_to("home")
        elif event.key in {pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER}:
            if self._entered_at_ms is not None and pygame.time.get_ticks() - self._entered_at_ms < 300:
                return
            if self._ready_to_capture() or self.manager.config.allow_manual_start_override:
                self.manual_override = not self._ready_to_capture()
                self.started_at_ms = pygame.time.get_ticks()
                self.message = "HOLD THAT ENERGY"
            else:
                self.message = "NEED ONE FACE IN EACH LANE"

    def handle_app_event(self, event: Any) -> None:
        return None

    def update(self, now_ms: int, dt_ms: int) -> None:
        if self._entered_at_ms is None:
            self._entered_at_ms = now_ms
        self._sync_faces()
        if self.finished:
            return
        if self.started_at_ms is None:
            return
        self._update_live_scores(now_ms)
        self._tick_display_scores(now_ms, dt_ms)
        if now_ms - self.started_at_ms >= self.live_score_duration_ms:
            self._finish_round()
        if self.sparkles is not None:
            self.sparkles.update(dt_ms)

    def render(self, surface: Any) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        fonts = self.fonts
        width, height = surface.get_size()
        if self.sparkles is None:
            self.sparkles = SparkleLayer(pygame, width, height, count=120)
        bg = scaled_asset_image(pygame, "mog_mirror_bg.png", (width, height))
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
        preview_rect = self.preview_renderer.render(
            surface,
            camera_rect,
            frame_bgr=frame,
            diagnostic=diagnostic,
            show_divider=self.manager.config.show_zone_divider,
            split_pane=self.manager.config.show_zone_divider,
        )
        faces = self._faces()
        self.face_renderer.render(
            surface,
            preview_rect or camera_rect.inflate(-6, -6),
            faces,
            split_x=self.manager.config.zone_split_x,
            point_mapper=self.preview_renderer.point_to_screen,
        )
        self._render_mirror_fx(pygame, surface, preview_rect or camera_rect.inflate(-6, -6), faces, pygame.time.get_ticks())

        panel_y = height - 120
        now_ms = pygame.time.get_ticks()

        for index, lane in enumerate(self.lanes):
            color = (255, 60, 160) if index == 0 else (0, 130, 255)

            if index == 0:
                rect = pygame.Rect(40, height - 210, 260, 120)
            else:
                rect = pygame.Rect(655, height - 210, 260, 120)

            self._draw_live_score(
                pygame,
                surface,
                rect,
                lane,
                color,
                now_ms,
            )

        countdown = self._countdown_label()
        if countdown is not None:
            draw_text(surface, countdown, fonts.title, (255, 220, 40), (width // 2, height // 2 - 70), anchor="center")

        draw_bottom_rule(pygame, surface, height - 44, width)
        help_text = "SPACE CAPTURES / ESC HOME"
        if not self._ready_to_capture() and self.manager.config.allow_manual_start_override:
            help_text = "SPACE MANUAL CAPTURE / ESC HOME"
        draw_text(surface, self.message, fonts.small, theme.TEXT_MUTED, (42, height - 32), max_width=width // 2)
        draw_text(surface, help_text, fonts.small, theme.TEXT_MUTED, (width - 42, height - 32), anchor="topright")
        if self.sparkles is not None:
            self.sparkles.render(surface)

        ##if self.phase == PHASE_GENERATING:
            ##self._render_generating_overlay(surface, width, height)

    # ------------------------------------------------------------------
    # Avatar mode
    # ------------------------------------------------------------------
    def _avatar_mode_enabled(self) -> bool:
        return False

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
            self._update_lane_movement(lane)
            target_index = self._display_target_bucket(now_ms)
            if force or lane.display_target_index != target_index:
                self._set_display_target(lane, now_ms)

    def _set_display_target(self, lane: MirrorLane, now_ms: int) -> None:
        aura = 45 if lane.live_score is None else lane.live_score
        face_bonus = 6 if lane.face is not None else -12
        movement_bonus = lane.movement_energy * 30.0
        target_index = self._display_target_bucket(now_ms)
        jitter = self._target_jitter(lane, target_index)
        target = max(1.0, min(100.0, aura * 0.72 + 14.0 + face_bonus + movement_bonus + jitter))
        delta = abs(target - lane.display_score)
        lane.display_score_target = target
        lane.display_score_rate = max(
            lane.display_score_rate,
            min(260.0, 70.0 + delta * 7.0 + lane.movement_energy * 160.0),
        )
        lane.display_pulse_until_ms = now_ms + 340
        lane.display_target_index = target_index

    def _tick_display_scores(self, now_ms: int, dt_ms: int) -> None:
        del now_ms
        dt_seconds = max(0.0, min(0.1, dt_ms / 1000.0))
        for lane in self.lanes:
            diff = lane.display_score_target - lane.display_score
            if abs(diff) > 0.5:
                step = min(abs(diff), max(45.0, lane.display_score_rate) * dt_seconds)
                lane.display_score += step if diff > 0 else -step
            lane.display_score = max(0.0, min(100.0, lane.display_score))
            lane.display_score_rate *= 0.90 ** max(1.0, dt_ms / 16.667)
            lane.movement_energy *= 0.94 ** max(1.0, dt_ms / 16.667)
            if lane.display_score_rate < 10.0:
                lane.display_score_rate = 0.0

    def _display_target_bucket(self, now_ms: int) -> int:
        if self.started_at_ms is None:
            return 0
        interval_ms = max(1, self.live_score_duration_ms // 5)
        elapsed_ms = max(0, now_ms - self.started_at_ms)
        return max(0, min(4, elapsed_ms // interval_ms))

    def _target_jitter(self, lane: MirrorLane, target_index: int) -> int:
        seed_text = f"{self.session_id or 'mirror'}:{lane.name}:{lane.zone}:{target_index}"
        return sum(ord(char) for char in seed_text) % 17 - 8

    def _update_lane_movement(self, lane: MirrorLane) -> None:
        face = lane.face
        if face is None:
            lane.last_face_center = None
            lane.last_face_box_area = None
            lane.movement_energy *= 0.65
            return
        center = face.get("center")
        bbox = face.get("bbox")
        if not isinstance(center, dict) or not isinstance(bbox, dict):
            lane.movement_energy *= 0.75
            return
        x = float(center.get("x", 0.0))
        y = float(center.get("y", 0.0))
        area = max(0.0, float(bbox.get("width", 0.0)) * float(bbox.get("height", 0.0)))
        instant = 0.0
        if lane.last_face_center is not None:
            dx = abs(x - lane.last_face_center[0])
            dy = abs(y - lane.last_face_center[1])
            instant += (dx + dy) * 7.0
        if lane.last_face_box_area is not None:
            instant += abs(area - lane.last_face_box_area) * 12.0
        lane.movement_energy = max(lane.movement_energy * 0.65, min(1.0, instant))
        lane.last_face_center = (x, y)
        lane.last_face_box_area = area

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
        heat = self._lane_heat(lane)
        text_color = self._heat_color(heat, color)
        score_value = max(1, min(100, int(round(lane.display_score))))
        image = self.fonts.card_title.render(str(score_value), True, text_color)
        scale = 1.0 + heat * 0.28 + (0.08 if lane.display_pulse_until_ms > now_ms else 0.0)
        size = (max(1, int(image.get_width() * scale)), max(1, int(image.get_height() * scale)))
        max_width = max(80, rect.width - 210)
        if size[0] > max_width:
            fit = max_width / size[0]
            size = (max(1, int(size[0] * fit)), max(1, int(size[1] * fit)))
        if size != image.get_size():
            image = pygame.transform.smoothscale(image, size)
        score_rect = image.get_rect(midright=(rect.right + 35, rect.bottom - 60))
        shadow = image.copy()
        shadow.fill((12, 32, 16), special_flags=pygame.BLEND_RGB_MULT)
        surface.blit(shadow, score_rect.move(2, 2))
        surface.blit(image, score_rect)
        if lane.display_score_rate > 35:
            draw_text(surface, f"+{int(lane.display_score_rate)}/s", self.fonts.small, text_color, (score_rect.right, score_rect.top - 14), anchor="topright")

    def _lane_heat(self, lane: MirrorLane | None) -> float:
        if lane is None:
            return 0.0
        return max(0.0, min(1.0, lane.display_score_rate / 260.0))

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
        snapshot = self.manager.camera_service.snapshot() if self.manager.camera_service is not None else None
        frame = snapshot.display_bgr if snapshot is not None else None
        self.manager.state.reveal_replay_image = frame
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
            crop = crop_upper_body(frame, lane.face, lane.zone)
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
                    "ai_job_ids": [],
                }
            )
        self.manager.leaderboard_service.complete_session(
            self.session_id,
            metadata={"manual_override": self.manual_override, "scores": {row["display_name"]: row["score"] for row in rows}},
        )
        self.manager.state.reveal_rows = rows
        self.manager.state.last_session_id = self.session_id
        self.manager.speak_voiceline("mog_mirror", "end")
        self.manager.go_to("score_reveal")

    def _average_live_score(self, lane: MirrorLane) -> int | None:
        if not lane.live_score_samples:
            return lane.live_score
        return round(sum(lane.live_score_samples) / len(lane.live_score_samples))
