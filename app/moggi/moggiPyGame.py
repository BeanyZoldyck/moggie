import os
import math
import pygame

pygame.init()

WIDTH, HEIGHT = 1280, 720
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("MOGGI Arcade")
clock = pygame.time.Clock()

ASSETS = "assets"

selected_game = 0
focused_area = "cards"
button_pressed = False

def load_image(filename, size=None):
    path = os.path.join(ASSETS, filename)

    if not os.path.exists(path):
        print("Missing asset:", path)
        return None

    image = pygame.image.load(path).convert_alpha()

    if size:
        image = pygame.transform.smoothscale(image, size)

    return image

arcade_bg = load_image("arcade_bg.png", (WIDTH, HEIGHT))

CARD_NORMAL_SIZE = (330, 470)
CARD_SELECTED_SIZE = (360, 520)
BUTTON_SIZE = (320, 170)
BUTTON_PRESSED_SIZE = (350, 200)
HIPPO_SIZE = (300, 450)

card_images = [
    {
        "normal": load_image("card_mirror.png", CARD_NORMAL_SIZE),
        "selected": load_image("card_mirror_selected.png", CARD_SELECTED_SIZE),
        "name": "Mog Mirror",
    },
    {
        "normal": load_image("card_sixseven.png", CARD_NORMAL_SIZE),
        "selected": load_image("card_sixseven_selected.png", CARD_SELECTED_SIZE),
        "name": "67 Challenge",
    },
    {
        "normal": load_image("card_emoji.png", CARD_NORMAL_SIZE),
        "selected": load_image("card_emoji_selected.png", CARD_SELECTED_SIZE),
        "name": "Emoji Face Match",
    },
]

lets_go = load_image("lets_go.png", BUTTON_SIZE)
lets_go_pressed = load_image("lets_go_pressed.png", BUTTON_PRESSED_SIZE)
moo_deng = load_image("moo_deng_pixel.png", HIPPO_SIZE)

card_centers = [
    (360, 355),
    (630, 355),
    (910, 355),
]

lets_go_center = (640, 540)
moo_deng_base_pos = (1000, 280)

small_font = pygame.font.Font(None, 32)

def draw_centered_image(img, center):
    if img:
        rect = img.get_rect(center=center)
        screen.blit(img, rect)

def draw_card(index):
    card = card_images[index]
    selected = index == selected_game and focused_area == "cards"
    img = card["selected"] if selected else card["normal"]
    draw_centered_image(img, card_centers[index])

def draw_start_button():
    if focused_area == "start":
        if button_pressed:
            img = lets_go
        else:
            img = lets_go_pressed
    else:
        img = lets_go

    draw_centered_image(img, lets_go_center)

def draw_moo_deng():
    if not moo_deng:
        return

    time_ms = pygame.time.get_ticks()

    cycle = (time_ms // 150) % 5

    offsets = [0, -2, -6, -8, -6, -2]

    bounce = offsets[cycle]

    x, y = moo_deng_base_pos


    screen.blit(
        moo_deng,
        (x, y + bounce)
    )

def start_selected_game():
    print("Starting:", card_images[selected_game]["name"])

running = True

while running:
    clock.tick(60)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False

            elif event.key == pygame.K_LEFT and focused_area == "cards":
                selected_game = (selected_game - 1) % len(card_images)

            elif event.key == pygame.K_RIGHT and focused_area == "cards":
                selected_game = (selected_game + 1) % len(card_images)

            elif event.key == pygame.K_DOWN:
                focused_area = "start"

            elif event.key == pygame.K_UP:
                focused_area = "cards"

            elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                if focused_area == "start":
                    button_pressed = True
                    start_selected_game()
                else:
                    focused_area = "start"

        if event.type == pygame.KEYUP:
            if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                button_pressed = False

    if arcade_bg:
        screen.blit(arcade_bg, (0, 0))
    else:
        screen.fill((20, 8, 45))

    for i in range(len(card_images)):
        draw_card(i)

    draw_start_button()
    draw_moo_deng()

    hint = small_font.render("SPACE TO SELECT!", True, (255, 255, 255))
    screen.blit(hint, hint.get_rect(center=(640, 600)))

    pygame.display.flip()

pygame.quit()