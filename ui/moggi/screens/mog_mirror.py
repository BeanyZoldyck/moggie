import pygame

from .common import draw_text, draw_video_divider, game_video_rect, load_image
from .game_logic import score_aura, winner_from_scores


class MogMirrorScreen:
    COUNTDOWN_SECONDS = 3
    SCAN_SECONDS = 3

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.bg = load_image("mog_mirror_bg.png", (width, height))
        self.big_font = pygame.font.Font(None, 120)
        self.med_font = pygame.font.Font(None, 72)
        self.small_font = pygame.font.Font(None, 36)
        self.reset()

    def reset(self):
        self.state = "ready"
        self.countdown_start = 0
        self.scan_start = 0
        self.session_id = str(pygame.time.get_ticks())
        self.player_one_score = 0
        self.player_two_score = 0
        self.winner = "tie"
        self.finished = False
        self.exit_to_menu = False
        self.latest_faces = {"player_one": None, "player_two": None}
        self.last_cv_frame_id = -1

    def set_faces(self, player_one_face=None, player_two_face=None):
        self.latest_faces["player_one"] = player_one_face
        self.latest_faces["player_two"] = player_two_face

    def start_countdown(self):
        self.state = "countdown"
        self.countdown_start = pygame.time.get_ticks()

    def start_scanning(self):
        self.state = "scanning"
        self.scan_start = pygame.time.get_ticks()

    def create_scores(self):
        p1_face = self.latest_faces["player_one"]
        p2_face = self.latest_faces["player_two"]

        self.player_one_score = score_aura(
            session_id=self.session_id,
            display_name="Player 1",
            zone="p1",
            face=p1_face,
            manual_override=True,
        )
        self.player_two_score = score_aura(
            session_id=self.session_id,
            display_name="Player 2",
            zone="p2",
            face=p2_face,
            manual_override=True,
        )
        self.winner = winner_from_scores(self.player_one_score, self.player_two_score)

    def update_cv(self, camera):
        if camera is None:
            return
        if camera.detection_frame_id == self.last_cv_frame_id:
            return

        self.last_cv_frame_id = camera.detection_frame_id
        self.set_faces(
            player_one_face=camera.face_for_zone("p1"),
            player_two_face=camera.face_for_zone("p2"),
        )

    def finish_round(self):
        self.create_scores()
        self.state = "done"
        self.finished = True

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_BACKSPACE:
            self.exit_to_menu = True
        elif event.key == pygame.K_SPACE and self.state == "ready":
            self.start_countdown()

    def update(self, dt):
        now = pygame.time.get_ticks()

        if self.state == "countdown":
            elapsed = (now - self.countdown_start) / 1000
            if elapsed >= self.COUNTDOWN_SECONDS + 1:
                self.start_scanning()

        elif self.state == "scanning":
            elapsed = (now - self.scan_start) / 1000
            if elapsed >= self.SCAN_SECONDS:
                self.finish_round()

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
            screen.fill((20, 8, 45))

        if camera is not None:
            camera.draw_split_preview(screen, video_rect, self.small_font)
            camera.draw_face_overlay(screen)

        draw_video_divider(screen, self.width, video_rect)

    def draw_countdown(self, screen):
        elapsed = (pygame.time.get_ticks() - self.countdown_start) / 1000
        number = self.COUNTDOWN_SECONDS - int(elapsed)

        if number > 0:
            draw_text(screen, str(number), self.big_font, (255, 220, 40), (640, 300))
        else:
            draw_text(screen, "SNAP!", self.big_font, (255, 60, 160), (640, 300))

    def draw_scanning(self, screen):
        elapsed = (pygame.time.get_ticks() - self.scan_start) / 1000
        progress = min(1, elapsed / self.SCAN_SECONDS)

        draw_text(screen, "SCANNING AURA...", self.med_font, (255, 220, 40), (640, 250))

        bar_x = 390
        bar_y = 300
        bar_w = 500
        bar_h = 28

        pygame.draw.rect(screen, (30, 10, 60), (bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(screen, (255, 255, 255), (bar_x, bar_y, bar_w, bar_h), 3)
        pygame.draw.rect(screen, (255, 60, 160), (bar_x, bar_y, int(bar_w * progress), bar_h))

    def draw(self, screen, camera=None):
        self.draw_background(screen, camera)

        if self.state == "ready":
            draw_text(screen, "SPACE TO SNAP", self.med_font, (255, 220, 40), (640, 300))
        elif self.state == "countdown":
            self.draw_countdown(screen)
        elif self.state == "scanning":
            self.draw_scanning(screen)
