from __future__ import annotations

from typing import Any

from app.core.app_event import EVENT_AI_JOB_UPDATE, AppEvent
from app.core.game_catalog import game_for_type
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


def _pygame() -> Any:
    import pygame

    return pygame


class ScoreRevealScreen:
    name = "score_reveal"

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.fonts: FontSet | None = None
        self.ai_job_statuses: dict[str, dict[str, Any]] = {}

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

    def handle_event(self, event: Any) -> None:
        pygame = _pygame()
        if event.type != pygame.KEYDOWN:
            return
        if event.key in {pygame.K_ESCAPE, pygame.K_h, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE}:
            self.manager.go_to("home")
        elif event.key == pygame.K_l:
            self.manager.go_to("leaderboard")

    def update(self, now_ms: int, dt_ms: int) -> None:
        return None

    def handle_app_event(self, event: AppEvent) -> None:
        if event.type != EVENT_AI_JOB_UPDATE:
            return
        job_id = event.payload.get("job_id")
        if not isinstance(job_id, str):
            return
        self.ai_job_statuses[job_id] = {
            "status": event.payload.get("status"),
            "kind": event.payload.get("metadata", {}).get("kind"),
            "metadata": event.payload.get("metadata", {}),
        }

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

        pygame.draw.rect(surface, (31, 24, 24), pygame.Rect(0, 0, width, 118))
        pygame.draw.rect(surface, game.accent, pygame.Rect(0, 118, width, 4))
        draw_text(surface, "PLAYERS LOCKED", fonts.title, theme.TEXT, (48, 30), max_width=width - 96)
        draw_text(surface, game.title, fonts.body, game.accent, (52, 92), max_width=width - 104)

        if game.game_type == "mog_mirror" and any(row.get("crop_bgr") is not None for row in rows):
            self._render_mog_mirror_portraits(pygame, surface, rows, fonts, width, height)
        else:
            self._render_score_rows(pygame, surface, rows, fonts, width)

        button_y = height - 132
        home_rect = pygame.Rect(width // 2 - 224, button_y, 196, 58)
        board_rect = pygame.Rect(width // 2 + 28, button_y, 196, 58)
        draw_button(pygame, surface, home_rect, "HOME", fonts.body, selected=True, accent=game.accent)
        draw_button(pygame, surface, board_rect, "BOARD", fonts.body, selected=False, accent=game.accent)
        draw_bottom_rule(pygame, surface, height - 44, width)
        draw_text(surface, "ENTER HOME / L BOARD", fonts.small, theme.TEXT_MUTED, (48, height - 32))

    def _render_score_rows(self, pygame: Any, surface: Any, rows: list[dict[str, Any]], fonts: FontSet, width: int) -> None:
        panel_w = min(920, width - 96)
        panel_x = (width - panel_w) // 2
        row_h = 132 if any(row.get("crop_bgr") is not None for row in rows) else 104
        start_y = 174
        for index, row in enumerate(rows):
            rect = pygame.Rect(panel_x, start_y + index * (row_h + 24), panel_w, row_h)
            color = theme.PLAYER_COLORS[index % len(theme.PLAYER_COLORS)]
            border = theme.WARNING if row.get("winner") else color
            draw_panel(pygame, surface, rect, fill=theme.SURFACE, border=border, width=2)
            crop_rect = pygame.Rect(rect.left + 18, rect.top + 14, 96, rect.height - 28)
            if row.get("crop_bgr") is not None:
                self._draw_crop(pygame, surface, crop_rect, row["crop_bgr"], color)
                text_x = crop_rect.right + 24
            else:
                text_x = rect.left + 86
            draw_text(surface, f"P{index + 1}", fonts.body, border, (rect.left + 26, rect.top + 18))
            winner_text = "WINNER" if row.get("winner") else str(row.get("label") or "")
            draw_text(
                surface,
                winner_text,
                fonts.small,
                border if row.get("winner") else theme.TEXT_MUTED,
                (rect.left + 26, rect.bottom - 34),
                max_width=90,
            )
            draw_text(
                surface,
                str(row["display_name"]),
                fonts.card_title,
                theme.TEXT,
                (text_x, rect.top + 24),
                max_width=rect.width - (text_x - rect.left) - 230,
            )
            self._draw_row_details(surface, row, fonts, text_x, rect)
            score = "--" if row.get("score") is None else str(row["score"])
            draw_text(surface, score, fonts.card_title, theme.TEXT, (rect.right - 34, rect.centery), anchor="midright")

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
        gap = 28
        available_h = max(320, height - 290)
        card_w = min(500, (width - 120 - gap) // max(1, len(visible_rows)))
        card_h = available_h
        total_w = card_w * len(visible_rows) + gap * (len(visible_rows) - 1)
        left = (width - total_w) // 2
        top = 154
        for index, row in enumerate(visible_rows):
            rect = pygame.Rect(left + index * (card_w + gap), top, card_w, card_h)
            color = theme.PLAYER_COLORS[index % len(theme.PLAYER_COLORS)]
            border = theme.WARNING if row.get("winner") else color
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

            crop_h = max(210, rect.height - 132)
            crop_w = min(rect.width - 48, int(crop_h * 0.72))
            crop_rect = pygame.Rect(0, 0, crop_w, crop_h)
            crop_rect.midtop = (rect.centerx, rect.top + 62)
            if row.get("crop_bgr") is not None:
                self._draw_crop(pygame, surface, crop_rect, row["crop_bgr"], border)

            score = "--" if row.get("score") is None else str(row["score"])
            draw_text(surface, score, fonts.title, theme.TEXT, (rect.right - 28, rect.bottom - 76), anchor="midright")
            label = "WINNER" if row.get("winner") else str(row.get("label") or "")
            rank = row.get("rank")
            if rank and not row.get("winner"):
                label = f"{label} / RANK #{rank}"
            draw_text(surface, label, fonts.small, border if row.get("winner") else theme.TEXT_MUTED, (rect.left + 28, rect.bottom - 72), max_width=rect.width - 170)
            ai_status = self._ai_status_label(row)
            if ai_status:
                draw_text(surface, ai_status, fonts.small, theme.ACCENT if "READY" in ai_status else theme.TEXT_MUTED, (rect.left + 28, rect.bottom - 40), max_width=rect.width - 56)

    def _draw_row_details(self, surface: Any, row: dict[str, Any], fonts: FontSet, text_x: int, rect: Any) -> None:
        label = str(row.get("label") or "")
        if label:
            rank = row.get("rank")
            label_text = f"{label} / RANK #{rank}" if rank else label
            draw_text(
                surface,
                label_text,
                fonts.small,
                theme.TEXT_MUTED,
                (text_x, rect.bottom - 38),
                max_width=rect.width - (text_x - rect.left) - 230,
            )
        ai_status = self._ai_status_label(row)
        if ai_status:
            draw_text(
                surface,
                ai_status,
                fonts.small,
                theme.ACCENT if "READY" in ai_status else theme.TEXT_MUTED,
                (text_x, rect.bottom - 20),
                max_width=rect.width - (text_x - rect.left) - 230,
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
