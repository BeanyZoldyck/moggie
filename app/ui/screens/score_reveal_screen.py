from __future__ import annotations

import logging
import queue
from pathlib import Path
from typing import Any

import shutil
import tempfile

from app.core.app_event import EVENT_AI_JOB_UPDATE, AppEvent
from app.core.game_catalog import game_for_type
from app.games.recap_prompts import RECAP_NEGATIVE_PROMPT, build_recap_prompt
from app.ui import theme
from app.ui.render_utils import (
    FontSet,
    build_fonts,
    draw_bottom_rule,
    draw_button,
    draw_panel,
    draw_text,
    scaled_asset_image,
)
from app.util.images import encode_bgr_jpeg
from app.util.video_playback import LoopingVideoPlayer, download_in_background

LOGGER = logging.getLogger(__name__)


def _pygame() -> Any:
    import pygame

    return pygame


class ScoreRevealScreen:
    name = "score_reveal"

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.fonts: FontSet | None = None
        self.ai_job_statuses: dict[str, dict[str, Any]] = {}
        # Optional, opt-in AI replay video state.
        self.replay_phase = "idle"  # idle | generating | downloading | ready | failed
        self.replay_job_id: str | None = None
        self.replay_player: LoopingVideoPlayer | None = None
        self.replay_error = ""
        self._replay_queue: "queue.Queue[tuple[Path | None, str]]" = queue.Queue()

    def on_enter(self, **_: Any) -> None:
        active_job_ids = {
            job_id
            for row in self.manager.state.reveal_rows
            for job_id in row.get("ai_job_ids", [])
        }
        self.ai_job_statuses = {
            job_id: status
            for job_id, status in self.ai_job_statuses.items()
            if job_id in active_job_ids
        }
        self._close_replay()
        self.replay_phase = "idle"
        self.replay_job_id = None
        self.replay_error = ""
        self._replay_queue: "queue.Queue[tuple[Path | None, str]]" = queue.Queue()

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_g:
            if self.replay_phase in {"idle", "failed"} and self._can_generate_replay():
                self._start_replay()
            return
        if event.key in {pygame.K_ESCAPE, pygame.K_h, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE}:
            self._close_replay()
            self.manager.go_to("home")
        elif event.key == pygame.K_l:
            self._close_replay()
            self.manager.go_to("leaderboard")

    def update(self, now_ms: int, dt_ms: int) -> None:
        self._drain_replay_queue()
        if self.replay_player is not None:
            self.replay_player.advance(now_ms)

    def handle_app_event(self, event: AppEvent) -> None:
        if event.type != EVENT_AI_JOB_UPDATE:
            return
        job_id = event.payload.get("job_id")
        if not isinstance(job_id, str):
            return
        metadata = event.payload.get("metadata", {})
        status = event.payload.get("status")
        self.ai_job_statuses[job_id] = {
            "status": status,
            "kind": metadata.get("kind"),
            "metadata": metadata,
        }
        if job_id != self.replay_job_id:
            return
        if status == "succeeded":
            result = metadata.get("result") or {}
            url = result.get("uri") or result.get("video_url")
            if isinstance(url, str) and url:
                LOGGER.info("Recap: generated video %s", url)
                self.replay_phase = "downloading"
                download_in_background(url, lambda path, u=url: self._replay_queue.put((path, u)))
            else:
                self.replay_phase = "failed"
                self.replay_error = "no video URL in result"
        elif status in {"failed", "timed_out"}:
            self.replay_phase = "failed"
            self.replay_error = str(metadata.get("error") or status)
            LOGGER.warning("Recap: job %s (%s)", status, self.replay_error)

    # ------------------------------------------------------------------
    # Replay generation
    # ------------------------------------------------------------------
    def _can_generate_replay(self) -> bool:
        config = getattr(self.manager, "config", None)
        service = getattr(self.manager, "ai_job_service", None)
        image = getattr(self.manager.state, "reveal_replay_image", None)
        return bool(
            config is not None
            and getattr(config, "enable_pika", False)
            and service is not None
            and image is not None
        )

    def _start_replay(self) -> None:
        service = self.manager.ai_job_service
        game_type = self.manager.state.selected_game_type
        image = self.manager.state.reveal_replay_image
        image_bytes = encode_bgr_jpeg(image)
        if not image_bytes:
            self.replay_phase = "failed"
            self.replay_error = "could not encode capture"
            return
        payload = {
            "game_type": game_type,
            "image_bytes": image_bytes,
            "image_mime_type": "image/jpeg",
            "prompt": build_recap_prompt(game_type, self.manager.state.reveal_rows),
            "negative_prompt": RECAP_NEGATIVE_PROMPT,
            "has_crop": True,
        }
        self.replay_job_id = service.submit(f"{game_type}.recap_video", payload)
        self.replay_phase = "generating"
        self.replay_error = ""
        LOGGER.info("Recap: submitted job %s for %s", self.replay_job_id, game_type)

    def _drain_replay_queue(self) -> None:
        while True:
            try:
                path, url = self._replay_queue.get_nowait()
            except queue.Empty:
                break
            if path is None:
                self.replay_phase = "failed"
                self.replay_error = "download failed"
                continue
            player = LoopingVideoPlayer(path)
            if not player.is_ready:
                player.close()
                self.replay_phase = "failed"
                self.replay_error = "could not open clip"
                continue
            self._close_replay()
            self.replay_player = player
            self.replay_phase = "ready"
            saved_path = self._save_replay(path, url)
            LOGGER.info("Recap: ready — tmp=%s saved=%s url=%s", path, saved_path, url)

    def _save_replay(self, tmp_path: Path, remote_url: str) -> Path | None:
        """Persist generated recap media locally and/or to S3, then record in DB."""
        config = getattr(self.manager, "config", None)
        if config is None:
            return None
        save_local = bool(getattr(config, "save_generated_media", False))
        save_s3 = bool(getattr(config, "enable_s3_video_storage", False))
        if not save_local and not save_s3:
            return None
        try:
            game_type = self.manager.state.selected_game_type
            session_id = getattr(self.manager.state, "last_session_id", None)
            leaderboard = getattr(self.manager, "leaderboard_service", None)
            local_dest: Path | None = None
            if save_local:
                media_dir: Path = config.media_dir
                media_dir.mkdir(parents=True, exist_ok=True)
                local_dest = media_dir / f"{game_type}_recap_{tmp_path.stem}.mp4"
                shutil.copy2(tmp_path, local_dest)
            if leaderboard is not None and session_id is not None:
                storage_mode = "local"
                uri = str(local_dest) if local_dest is not None else remote_url
                metadata: dict[str, Any] = {"remote_url": remote_url, "game_type": game_type}
                storage = getattr(self.manager, "storage_service", None)
                if save_s3 and storage is not None:
                    upload = storage.upload_video(tmp_path, game_type, session_id)
                    storage_mode = "s3"
                    uri = upload["url"]
                    metadata.update(upload)
                    if local_dest is not None:
                        metadata["local_path"] = str(local_dest)
                leaderboard.record_media_asset(
                    session_id,
                    f"{game_type}.recap_video",
                    uri,
                    storage_mode=storage_mode,
                    metadata=metadata,
                )
            if local_dest is not None:
                LOGGER.info("Recap saved to %s", local_dest)
            return local_dest
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Recap save failed: %s", exc)
            return None

    def _close_replay(self) -> None:
        if self.replay_player is not None:
            try:
                self.replay_player.close()
            except Exception:  # noqa: BLE001
                pass
            self.replay_player = None

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def render(self, surface: Any) -> None:
        pygame = _pygame()
        self.fonts = self.fonts or build_fonts(pygame)
        fonts = self.fonts
        width, height = surface.get_size()

        game = game_for_type(self.manager.state.selected_game_type)
        rows = self.manager.state.reveal_rows or [
            {"display_name": name, "score": None, "label": "READY"}
            for name in self.manager.state.player_names
        ]
        if not rows:
            rows = [{"display_name": "Player 1", "score": None, "label": "READY"}]

        winners = [row for row in rows if row.get("winner")]
        if len(winners) == 1:
            player_index = rows.index(winners[0])
            win_asset = "player1_win.png" if player_index == 0 else "player2_win.png"
        else:
            win_asset = "tie.png"
        win_bg = scaled_asset_image(pygame, win_asset, (width, height))
        if win_bg is not None:
            surface.blit(win_bg, (0, 0))
        else:
            surface.fill(theme.BACKGROUND)

        if game.game_type == "mog_mirror" and any(row.get("crop_bgr") is not None for row in rows):
            self._render_mog_mirror_portraits(pygame, surface, rows, fonts, width, height)
        else:
            self._render_score_rows(pygame, surface, rows, fonts, width)

        if self.replay_phase == "ready":
            self._render_replay_video(pygame, surface, fonts, width, height)
        elif self.replay_phase in {"generating", "downloading"}:
            self._render_replay_generating(pygame, surface, fonts, width, height)

    def _render_replay_hint(self, surface: Any, fonts: FontSet, width: int, height: int) -> None:
        nav = "ENTER HOME / L BOARD"
        if self._can_generate_replay():
            if self.replay_phase == "idle":
                nav = "G AI REPLAY / ENTER HOME / L BOARD"
            elif self.replay_phase == "failed":
                nav = f"REPLAY FAILED ({self.replay_error}) — G RETRY / ENTER HOME"
            elif self.replay_phase == "ready":
                nav = "AI REPLAY READY / ENTER HOME / L BOARD"
        draw_text(surface, nav, fonts.small, theme.TEXT_MUTED, (48, height - 32), max_width=width - 96)

    def _render_replay_generating(self, pygame: Any, surface: Any, fonts: FontSet, width: int, height: int) -> None:
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        surface.blit(overlay, (0, 0))
        dots = "." * (1 + (pygame.time.get_ticks() // 500) % 3)
        verb = "GENERATING REPLAY" if self.replay_phase == "generating" else "DOWNLOADING REPLAY"
        draw_text(surface, f"{verb}{dots}", fonts.masthead, theme.ACCENT, (width // 2, height // 2 - 20), anchor="center")
        draw_text(surface, "one clip from both sides — this can take a bit", fonts.body, theme.TEXT, (width // 2, height // 2 + 36), anchor="center")

    def _render_replay_video(self, pygame: Any, surface: Any, fonts: FontSet, width: int, height: int) -> None:
        frame = self.replay_player.current_frame_bgr() if self.replay_player is not None else None
        if frame is None:
            return
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        surface.blit(overlay, (0, 0))
        draw_text(surface, "AI REPLAY", fonts.title, theme.ACCENT, (width // 2, 80), anchor="center")
        video_rect = pygame.Rect(0, 0, min(width - 120, 960), min(height - 240, 560))
        video_rect.center = (width // 2, height // 2)
        self._draw_crop(pygame, surface, video_rect, frame, theme.ACCENT)
        draw_text(surface, "ENTER / ESC HOME", fonts.small, theme.TEXT_MUTED, (width // 2, height - 70), anchor="center")

    def _render_score_rows(self, pygame: Any, surface: Any, rows: list[dict[str, Any]], fonts: FontSet, width: int) -> None:
        panel_w = min(920, width - 96)
        panel_x = (width - panel_w) // 2
        row_h = 132 if any(row.get("crop_bgr") is not None for row in rows) else 104
        start_y = 260
        for index, row in enumerate(rows):
            rect = pygame.Rect(panel_x, start_y + index * row_h, panel_w, row_h)
            color = (0, 130, 255) if index == 0 else (255, 60, 160)
            border = theme.WARNING if row.get("winner") else color
            self._draw_winner_fx(pygame, surface, rect, border, active=bool(row.get("winner")))
            draw_panel(pygame, surface, rect, fill=(20, 45, 95), border=border, width=2)
            crop_rect = pygame.Rect(rect.left + 18, rect.top + 14, 96, rect.height - 28)
            if row.get("crop_bgr") is not None:
                self._draw_crop(pygame, surface, crop_rect, row["crop_bgr"], color)
                text_x = crop_rect.right + 24
            else:
                text_x = rect.left + 86
            draw_text(surface, f"P{index + 1}", fonts.body, border, (rect.left + 26, rect.top + 18))
            self._draw_row_details(surface, row, fonts, text_x, rect)
            score = "--" if row.get("score") is None else str(row["score"])
            if row.get("winner"):
                draw_text(
                    surface,
                    "WINNER",
                    fonts.body,
                    theme.WARNING,
                    (rect.centerx, rect.centery - 28),
                    anchor="center",
                )
            self._draw_score_pop(pygame, surface, score, fonts.card_title, theme.TEXT, (rect.right - 50, rect.centery), active=bool(row.get("winner")))


    def _render_mog_mirror_portraits(
        self,
        pygame: Any,
        surface: Any,
        rows: list[dict[str, Any]],
        fonts: FontSet,
        width: int,
        height: int,
    ) -> None:
        visible_rows = rows[:2]
        gap = 0
        available_h = max(320, height - 300)
        card_w = min(420, (width - 240) // 2)
        card_h = min(470, available_h)
        total_w = card_w * 2 + gap
        left = (width - total_w) // 2
        top = 120
        for index, row in enumerate(visible_rows):
            rect = pygame.Rect(left + index * (card_w + gap), top, card_w, card_h)
            color = (0, 130, 255) if index == 0 else (255, 60, 160)
            border = color
            draw_panel(pygame, surface, rect, fill=theme.SURFACE, border=border, width=3)
            draw_text(surface, f"P{index + 1}", fonts.body, border, (rect.left + 24, rect.top + 18))
            draw_text(
                surface,
                str(row["display_name"]),
                fonts.card_title,
                theme.TEXT,
                (rect.left + 78, rect.top + 12),
                max_width=rect.width - 106,
            )

            crop_h = max(190, rect.height - 170)
            crop_w = min(rect.width - 140, int(crop_h * 0.72))
            crop_rect = pygame.Rect(0, 0, crop_w, crop_h)
            crop_rect.midtop = (rect.centerx, rect.top + 62)
            if row.get("crop_bgr") is not None:
                self._draw_crop(pygame, surface, crop_rect, row["crop_bgr"], border)

            score = "--" if row.get("score") is None else str(row["score"])
            draw_text(surface, score, fonts.masthead, theme.TEXT, (rect.right - 28, rect.bottom - 76), anchor="midright")
            label = "WINNER" if row.get("winner") else str(row.get("label") or "")
            rank = row.get("rank")
            if rank and not row.get("winner"):
                label = f"{label} / RANK #{rank}"
            draw_text(surface, label, fonts.small, border if row.get("winner") else theme.TEXT_MUTED, (rect.left + 28, rect.bottom - 72), max_width=rect.width - 170)

    def _draw_row_details(self, surface: Any, row: dict[str, Any], fonts: FontSet, text_x: int, rect: Any) -> None:
        label = str(row.get("label") or "")
        if label:
            rank = row.get("rank")
            label_text = f"{label} / RANK #{rank}" if rank else label
            draw_text(
                surface,
                label_text,
                fonts.body,
                theme.TEXT,
                (rect.centerx, rect.centery),
                anchor="center",
            )

    def _draw_crop(
        self,
        pygame: Any,
        surface: Any,
        rect: Any,
        crop_bgr: Any,
        border: tuple[int, int, int],
    ) -> None:
        pygame.draw.rect(surface, theme.SURFACE_DARK, rect, border_radius=8)
        try:
            rgb = crop_bgr[:, :, ::-1]
            h, w = rgb.shape[:2]
            image = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB").convert()
            inner = rect.inflate(-8, -8)
            scale = max(inner.width / w, inner.height / h)
            scaled_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            image = pygame.transform.smoothscale(image, scaled_size)
            image_rect = image.get_rect(center=inner.center)
            previous_clip = surface.get_clip()
            surface.set_clip(inner)
            surface.blit(image, image_rect)
            surface.set_clip(previous_clip)
        except Exception:
            draw_text(surface, "NO CROP", self.fonts.small, theme.TEXT_MUTED, rect.center, anchor="center")
        pygame.draw.rect(surface, border, rect, 2, border_radius=8)

    def _ai_status_label(self, row: dict[str, Any]) -> str:
        job_ids = list(row.get("ai_job_ids", []))
        if not job_ids:
            return "LOCAL FALLBACK"
        statuses = [
            self.ai_job_statuses.get(job_id, {}).get("status", "queued")
            for job_id in job_ids
        ]
        if any(status in {"queued", "running"} for status in statuses):
            return "AI MEDIA RUNNING"
        if any(status == "succeeded" for status in statuses):
            return "AI MEDIA READY"
        if any(status in {"failed", "timed_out"} for status in statuses):
            return "AI MEDIA FALLBACK"
        return "AI MEDIA QUEUED"

    def _draw_winner_fx(self, pygame: Any, surface: Any, rect: Any, color: tuple[int, int, int], *, active: bool) -> None:
        if not active:
            return
        now_ms = pygame.time.get_ticks()
        pulse = int((now_ms // 90) % 12)
        glow = rect.inflate(18 + pulse, 18 + pulse)
        pygame.draw.rect(surface, (66, 50, 28), glow, 2, border_radius=10)
        pygame.draw.rect(surface, color, rect.inflate(8, 8), 2, border_radius=10)
        for index in range(8):
            x = rect.left + int((now_ms // 7 + index * 93) % max(1, rect.width))
            y = rect.top - 8 if index % 2 == 0 else rect.bottom + 8
            pygame.draw.line(surface, color, (x, y), (x + 20, y + (10 if index % 2 == 0 else -10)), 2)

    def _draw_score_pop(
        self,
        pygame: Any,
        surface: Any,
        score: str,
        font: Any,
        color: tuple[int, int, int],
        position: tuple[int, int],
        *,
        active: bool,
    ) -> None:
        image = font.render(score, True, theme.WARNING if active else color)
        if active:
            pulse = 1.0 + ((pygame.time.get_ticks() // 120) % 4) * 0.025
            image = pygame.transform.smoothscale(
                image,
                (max(1, int(image.get_width() * pulse)), max(1, int(image.get_height() * pulse))),
            )
        rect = image.get_rect(midright=position)
        shadow = image.copy()
        shadow.fill((36, 22, 12), special_flags=pygame.BLEND_RGB_MULT)
        surface.blit(shadow, rect.move(3, 3))
        surface.blit(image, rect)
