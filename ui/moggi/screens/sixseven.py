import pygame

from .common import draw_text, draw_video_divider, format_timer, game_video_rect, load_image
from .game_logic import SixtySevenCounter, winner_from_scores


class SixSevenScreen:
    ROUND_SECONDS = 30

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.bg = load_image("sixseven_bg.png", (width, height))
        self.timer_font = pygame.font.Font(None, 56)
        self.score_font = pygame.font.Font(None, 96)
        self.status_font = pygame.font.Font(None, 58)
        self.small_font = pygame.font.Font(None, 34)
        self.p1_counter = SixtySevenCounter()
        self.p2_counter = SixtySevenCounter()
        self.reset()

    def reset(self):
        self.state = "ready"
        self.round_start_time = 0
        self.player_one_score = 0
        self.player_two_score = 0
        self.winner = "tie"
        self.finished = False
        self.exit_to_menu = False
        self.last_cv_frame_id = -1
        self.needs_camera_counter_reset = True
        self.p1_counter.reset()
        self.p2_counter.reset()

    def start_round(self):
        self.state = "playing"
        self.round_start_time = pygame.time.get_ticks()
        self.player_one_score = 0
        self.player_two_score = 0
        self.finished = False
        self.needs_camera_counter_reset = True
        self.p1_counter.reset()
        self.p2_counter.reset()

    def add_rep(self, player):
        if self.state != "playing":
            return

        if player == "player_one":
            self.player_one_score += 1
        else:
            self.player_two_score += 1

    def update_player_hands(self, player, hands, frame_timestamp_ms):
        if self.state != "playing":
            return

        now_ms = pygame.time.get_ticks()
        counter = self.p1_counter if player == "player_one" else self.p2_counter
        reps = counter.update_from_hands(hands, now_ms=now_ms, frame_timestamp_ms=frame_timestamp_ms)

        if player == "player_one":
            self.player_one_score = reps
        else:
            self.player_two_score = reps

    def update_cv(self, camera):
        if self.state != "playing" or camera is None:
            return

        if self.needs_camera_counter_reset and hasattr(camera, "reset_motion_counts"):
            camera.reset_motion_counts()
            self.needs_camera_counter_reset = False

        if camera.detection_frame_id == self.last_cv_frame_id:
            return

        self.last_cv_frame_id = camera.detection_frame_id
        hands = list(camera.hands)
        landmark_hands = [hand for hand in hands if hand.get("source") != "motion"]

        if landmark_hands:
            self.update_player_hands(
                "player_one",
                [hand for hand in landmark_hands if hand.get("zone") == "p1"],
                camera.timestamp_ms,
            )
            self.update_player_hands(
                "player_two",
                [hand for hand in landmark_hands if hand.get("zone") == "p2"],
                camera.timestamp_ms,
            )
        else:
            self.player_one_score = camera.motion_reps["player_one"]
            self.player_two_score = camera.motion_reps["player_two"]

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
            self.start_round()
        elif event.key == pygame.K_a:
            self.add_rep("player_one")
        elif event.key == pygame.K_l:
            self.add_rep("player_two")

    def update(self, dt):
        if self.state != "playing":
            return

        elapsed = (pygame.time.get_ticks() - self.round_start_time) / 1000
        if elapsed >= self.ROUND_SECONDS:
            self.finish_round()

    def get_result(self):
        return {
            "winner": self.winner,
            "player_one_score": self.player_one_score,
            "player_two_score": self.player_two_score,
        }

    def current_video_rect(self):
        return game_video_rect(active=self.state != "ready")

    def draw_timer(self, screen):
        if self.state == "playing":
            elapsed = (pygame.time.get_ticks() - self.round_start_time) / 1000
            remaining = self.ROUND_SECONDS - elapsed
        else:
            remaining = self.ROUND_SECONDS

        draw_text(
            screen,
            format_timer(remaining),
            self.timer_font,
            (255, 220, 40),
            (640, 515),
        )

    def draw_scores(self, screen):
        p1 = str(self.player_one_score).zfill(2)
        p2 = str(self.player_two_score).zfill(2)

        draw_text(screen, p1, self.score_font, (255, 60, 160), (270, 555))
        draw_text(screen, p2, self.score_font, (0, 130, 255), (1005, 555))

    def draw(self, screen, camera=None):
        video_rect = self.current_video_rect()

        if self.bg:
            screen.blit(self.bg, (0, 0))
        else:
            screen.fill((15, 5, 35))

        if camera is not None:
            camera.draw_split_preview(screen, video_rect, self.small_font)
            camera.draw_hand_overlay(screen)

        draw_video_divider(screen, self.width, video_rect)
        self.draw_timer(screen)
        self.draw_scores(screen)

        if self.state == "ready":
            draw_text(
                screen,
                "SPACE TO START",
                self.status_font,
                (255, 220, 40),
                (640, 300),
            )
        elif self.state == "playing":
            draw_text(
                screen,
                "COUNT!",
                self.status_font,
                (255, 60, 160),
                (640, 300),
            )
