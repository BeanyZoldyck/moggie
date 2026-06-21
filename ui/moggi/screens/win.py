import pygame

from .common import draw_text, load_image
from .game_logic import normalize_winner


class WinScreen:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.player_one_win = load_image("player1_win.png", (width, height))
        self.player_two_win = load_image("player2_win.png", (width, height))
        self.tie = load_image("tie.png", (width, height))
        self.small_font = pygame.font.Font(None, 32)

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return None

        if event.key in (pygame.K_SPACE, pygame.K_RETURN):
            return "replay"
        if event.key in (pygame.K_BACKSPACE, pygame.K_ESCAPE):
            return "menu"

        return None

    def draw(self, screen, winner, player_one_score, player_two_score):
        winner = normalize_winner(winner, player_one_score, player_two_score)

        if winner == "player_one" and self.player_one_win:
            screen.blit(self.player_one_win, (0, 0))
        elif winner == "player_two" and self.player_two_win:
            screen.blit(self.player_two_win, (0, 0))
        elif winner == "tie" and self.tie:
            screen.blit(self.tie, (0, 0))
        else:
            screen.fill((20, 8, 45))
            label = "TIE" if winner == "tie" else f"{winner.replace('_', ' ').upper()} WINS"
            draw_text(screen, label, self.small_font, (255, 255, 255), (640, 500))

        draw_text(
            screen,
            f"P1: {player_one_score}   P2: {player_two_score}",
            self.small_font,
            (255, 255, 255),
            (640, 560),
        )
        draw_text(
            screen,
            "SPACE TO PLAY AGAIN   BACKSPACE TO MENU",
            self.small_font,
            (255, 255, 255),
            (640, 620),
        )
