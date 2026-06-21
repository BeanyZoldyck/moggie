import pygame

from .common import draw_text, draw_video_divider, format_timer, game_video_rect, load_image
from .game_logic import (
    build_expression_sequence,
    evaluate_match,
    expression_glyph,
    expression_label,
    features_for_expression,
    winner_from_scores,
)


class EmojiMatchScreen:
    ROUND_SECONDS = 30
    COUNTDOWN_SECONDS = 3
    TARGET_SECONDS = 4

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.bg = load_image("emoji_bg.png", (width, height))
        self.timer_font = pygame.font.Font(None, 64)
        self.big_font = pygame.font.Font(None, 120)
        self.med_font = pygame.font.Font(None, 72)
        self.small_font = pygame.font.Font(None, 36)
        self.reset()

    def reset(self):
        self.state = "ready"
        self.countdown_start = 0
        self.round_start = 0
        self.target_start = 0
        self.target_index = 0
        self.sequence = build_expression_sequence(str(pygame.time.get_ticks()), 20)
        self.player_one_score = 0
        self.player_two_score = 0
        self.player_one_hits = 0
        self.player_two_hits = 0
        self.winner = "tie"
        self.finished = False
        self.exit_to_menu = False
        self.last_cv_frame_id = -1
        self.last_cv_score_ms = {"player_one": -1_000_000, "player_two": -1_000_000}

    @property
    def current_target(self):
        return self.sequence[self.target_index % len(self.sequence)]

    def start_countdown(self):
        self.state = "countdown"
        self.countdown_start = pygame.time.get_ticks()

    def start_round(self):
        self.state = "game"
        now = pygame.time.get_ticks()
        self.round_start = now
        self.target_start = now

    def advance_target(self):
        self.target_index += 1
        self.target_start = pygame.time.get_ticks()

    def ensure_supported_target(self, supported_expressions):
        supported = set(supported_expressions)
        attempts = 0
        while self.current_target not in supported and attempts < len(self.sequence):
            self.advance_target()
            attempts += 1

    def record_expression(self, player, features):
        if self.state != "game":
            return

        result = evaluate_match(self.current_target, features)

        if player == "player_one":
            self.player_one_score += result.points
            if result.hit:
                self.player_one_hits += 1
        else:
            self.player_two_score += result.points
            if result.hit:
                self.player_two_hits += 1

        if result.hit:
            self.advance_target()

    def record_debug_hit(self, player):
        self.record_expression(player, features_for_expression(self.current_target))

    def update_cv(self, camera):
        if self.state != "game" or camera is None:
            return
        if camera.detection_frame_id == self.last_cv_frame_id:
            return

        self.last_cv_frame_id = camera.detection_frame_id
        supported_expressions = getattr(camera, "supported_expressions", (self.current_target,))
        self.ensure_supported_target(supported_expressions)
        now = pygame.time.get_ticks()
        players = [
            ("player_one", camera.face_for_zone("p1")),
            ("player_two", camera.face_for_zone("p2")),
        ]

        for player, face in players:
            if face is None:
                continue
            if now - self.last_cv_score_ms[player] < 650:
                continue

            target_before = self.current_target
            self.record_expression(player, face.get("expression_features", {}))
            self.last_cv_score_ms[player] = now

            if self.current_target != target_before:
                self.ensure_supported_target(supported_expressions)
                break

    def finish_round(self):
        self.state = "done"
        self.winner = winner_from_scores(self.player_one_score, self.player_two_score)
        self.finished = True

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_BACKSPACE:
            self.exit_to_menu = True
        elif event.key == pygame.K_SPACE and self.state == "ready":
            self.start_countdown()
        elif event.key == pygame.K_a:
            self.record_debug_hit("player_one")
        elif event.key == pygame.K_l:
            self.record_debug_hit("player_two")

    def update(self, dt):
        now = pygame.time.get_ticks()

        if self.state == "countdown":
            elapsed = (now - self.countdown_start) / 1000
            if elapsed >= self.COUNTDOWN_SECONDS + 1:
                self.start_round()

        elif self.state == "game":
            round_elapsed = (now - self.round_start) / 1000
            target_elapsed = (now - self.target_start) / 1000

            if round_elapsed >= self.ROUND_SECONDS:
                self.finish_round()
            elif target_elapsed >= self.TARGET_SECONDS:
                self.advance_target()

    def get_result(self):
        return {
            "winner": self.winner,
            "player_one_score": self.player_one_score,
            "player_two_score": self.player_two_score,
        }

    def current_video_rect(self):
        return game_video_rect(active=self.state != "ready")

    def draw_background(self, screen, camera=None):
        video_rect = self.current_video_rect()

        if self.bg:
            screen.blit(self.bg, (0, 0))
        else:
            screen.fill((15, 5, 40))

        if camera is not None:
            camera.draw_split_preview(screen, video_rect, self.small_font)
            camera.draw_face_overlay(screen)

        draw_video_divider(screen, self.width, video_rect)

    def draw_timer(self, screen):
        elapsed = (pygame.time.get_ticks() - self.round_start) / 1000
        remaining = self.ROUND_SECONDS - elapsed
        draw_text(screen, format_timer(remaining), self.timer_font, (255, 220, 40), (640, 550))

    def draw_scores(self, screen):
        draw_text(screen, self.player_one_score, self.small_font, (50, 255, 120), (470, 575))
        draw_text(screen, self.player_two_score, self.small_font, (255, 60, 160), (810, 575))

    def draw_countdown(self, screen):
        elapsed = (pygame.time.get_ticks() - self.countdown_start) / 1000
        value = self.COUNTDOWN_SECONDS - int(elapsed)

        if value > 0:
            draw_text(screen, str(value), self.big_font, (255, 220, 40), (640, 300))
        else:
            draw_text(screen, "GO!", self.big_font, (255, 60, 160), (640, 300))

    def draw_target(self, screen):
        target = self.current_target
        draw_text(screen, expression_glyph(target), self.big_font, (255, 255, 255), (640, 280))
        draw_text(screen, expression_label(target), self.med_font, (255, 220, 40), (640, 405))

    def draw(self, screen, camera=None):
        self.draw_background(screen, camera)

        if self.state == "ready":
            draw_text(screen, "SPACE TO START", self.med_font, (255, 220, 40), (640, 300))
        elif self.state == "countdown":
            self.draw_countdown(screen)
        elif self.state == "game":
            self.draw_target(screen)
            self.draw_timer(screen)
            self.draw_scores(screen)
