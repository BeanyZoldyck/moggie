from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.games.mog_mirror import crop_upper_body, label_for_aura, score_aura
from app.ui import theme
from app.ui.render_utils import FontSet, build_fonts, draw_bottom_rule, draw_panel, draw_text, scaled_asset_image
from app.ui.renderers.camera_preview_renderer import CameraPreviewRenderer
from app.ui.renderers.face_overlay_renderer import FaceOverlayRenderer
from app.util.images import encode_bgr_jpeg


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

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.manager.go_to("home")
        elif event.key in {pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER}:
            if self._ready_to_capture() or self.manager.config.allow_manual_start_override:
                self.manual_override = not self._ready_to_capture()
                self.started_at_ms = pygame.time.get_ticks()
                self.message = "HOLD THAT ENERGY"
            else:
                self.message = "NEED ONE FACE IN EACH LANE"

    def handle_app_event(self, event: Any) -> None:
        return None

    def update(self, now_ms: int, dt_ms: int) -> None:
        self._sync_faces()
        if self.finished:
            return
        if self.started_at_ms is None:
            return
        elapsed_ms = now_ms - self.started_at_ms
        self._update_live_scores(now_ms)
        if elapsed_ms >= self.live_score_duration_ms:
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
        )

        panel_y = height - 170
        lane_w = (width - 108 - 24) // 2
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
                score_text = "--" if lane.live_score is None else f"{lane.live_score}"
                draw_text(surface, "MOG SCORE", fonts.small, theme.TEXT_MUTED, (rect.right - 24, rect.top + 18), anchor="topright")
                draw_text(surface, score_text, fonts.card_title, color, (rect.right - 24, rect.bottom - 54), anchor="midright")

        countdown = self._countdown_label()
        if countdown is not None:
            draw_text(surface, countdown, fonts.masthead, theme.ACCENT, (width // 2, height // 2), anchor="center")

        draw_bottom_rule(pygame, surface, height - 44, width)
        help_text = "SPACE CAPTURES / ESC HOME"
        if not self._ready_to_capture() and self.manager.config.allow_manual_start_override:
            help_text = "SPACE MANUAL CAPTURE / ESC HOME"
        draw_text(surface, self.message, fonts.small, theme.TEXT_MUTED, (42, height - 32), max_width=width // 2)
        draw_text(surface, help_text, fonts.small, theme.TEXT_MUTED, (width - 42, height - 32), anchor="topright")

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

    def _finish_round(self) -> None:
        if self.finished or self.session_id is None:
            return
        self.finished = True
        now_ms = self.started_at_ms + self.live_score_duration_ms if self.started_at_ms is not None else 0
        self._update_live_scores(now_ms, force=True)
        snapshot = self.manager.camera_service.snapshot() if self.manager.camera_service is not None else None
        frame = snapshot.display_bgr if snapshot is not None else None
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
            ai_job_ids = self._submit_ai_jobs(lane, crop, score, label)
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
        self.manager.go_to("score_reveal")

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
        if self.manager.config.enable_pika:
            payload["request_pika_video"] = True
            payload["video_prompt"] = (
                "Create a short, sensational arcade replay from this Mog Mirror portrait. "
                "Make it glossy, dramatic, funny, and score-reveal worthy."
            )
        if self.manager.config.enable_image_generation:
            image_bytes = encode_bgr_jpeg(crop)
            if image_bytes:
                payload["image_bytes"] = image_bytes
                payload["image_mime_type"] = "image/jpeg"
            job_ids.append(service.submit("mog_mirror.caricature", payload))
        if (
            self.manager.config.enable_pika
            and not self.manager.config.enable_image_generation
            and (payload.get("image_url") or payload.get("source_uri"))
        ):
            job_ids.append(service.submit("mog_mirror.victory_video", payload))
        return job_ids
