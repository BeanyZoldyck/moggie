import math

import pygame

from .common import draw_centered_image, draw_text, load_image


class MenuScreen:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.selected_index = 0
        self.focused_area = "cards"
        self.button_pressed = False
        self.start_game = False

        self.arcade_bg = load_image("arcade_bg.png", (width, height))
        self.lets_go = load_image("lets_go.png", (320, 170))
        self.lets_go_pressed = load_image("lets_go_pressed.png", (350, 200))
        self.moo_deng = load_image("moo_deng_pixel.png", (300, 450))

        self.cards = [
            {
                "game_id": "mogmirror",
                "normal": load_image("card_mirror.png", (330, 470)),
                "selected": load_image("card_mirror_selected.png", (360, 520)),
            },
            {
                "game_id": "sixseven",
                "normal": load_image("card_sixseven.png", (330, 470)),
                "selected": load_image("card_sixseven_selected.png", (360, 520)),
            },
            {
                "game_id": "emoji",
                "normal": load_image("card_emoji.png", (330, 470)),
                "selected": load_image("card_emoji_selected.png", (360, 520)),
            },
        ]

        self.card_centers = [(360, 355), (630, 355), (910, 355)]
        self.lets_go_center = (640, 540)
        self.moo_deng_base_pos = (1000, 280)
        self.small_font = pygame.font.Font(None, 32)

    @property
    def selected_game(self):
        return self.cards[self.selected_index]["game_id"]

    def reset(self):
        self.focused_area = "cards"
        self.button_pressed = False
        self.start_game = False

    def consume_start_game(self):
        selected_game = self.selected_game
        self.start_game = False
        self.button_pressed = False
        return selected_game

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT and self.focused_area == "cards":
                self.selected_index = (self.selected_index - 1) % len(self.cards)
            elif event.key == pygame.K_RIGHT and self.focused_area == "cards":
                self.selected_index = (self.selected_index + 1) % len(self.cards)
            elif event.key == pygame.K_DOWN:
                self.focused_area = "start"
            elif event.key == pygame.K_UP:
                self.focused_area = "cards"
            elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                if self.focused_area == "start":
                    self.button_pressed = True
                else:
                    self.focused_area = "start"

        elif event.type == pygame.KEYUP:
            if event.key in (pygame.K_SPACE, pygame.K_RETURN) and self.button_pressed:
                self.start_game = True
                self.button_pressed = False

    def update(self, dt):
        pass

    def draw(self, screen):
        if self.arcade_bg:
            screen.blit(self.arcade_bg, (0, 0))
        else:
            screen.fill((20, 8, 45))

        for index, card in enumerate(self.cards):
            selected = index == self.selected_index
            image = card["selected"] if selected else card["normal"]
            draw_centered_image(screen, image, self.card_centers[index])

        button_image = self.lets_go
        if self.focused_area == "start" or self.button_pressed:
            button_image = self.lets_go_pressed
        draw_centered_image(screen, button_image, self.lets_go_center)

        if self.moo_deng:
            bob = int(math.sin(pygame.time.get_ticks() * 0.009) * 8)
            x, y = self.moo_deng_base_pos
            screen.blit(self.moo_deng, (x, y + bob))

        draw_text(
            screen,
            "SPACE TO SELECT!",
            self.small_font,
            (255, 255, 255),
            (640, 600),
        )
