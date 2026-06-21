import os

import pygame


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
READY_GAME_VIDEO_RECT = (85, 130, 1110, 335)
ACTIVE_GAME_VIDEO_RECT = (40, 75, 1200, 420)


def asset_path(filename):
    direct_path = os.path.join(ASSETS_DIR, filename)
    if os.path.exists(direct_path):
        return direct_path

    wanted = filename.lower()
    for asset_name in os.listdir(ASSETS_DIR):
        if asset_name.lower() == wanted:
            return os.path.join(ASSETS_DIR, asset_name)

    return direct_path


def load_image(filename, size=None):
    path = asset_path(filename)

    if not os.path.exists(path):
        print("Missing asset:", path)
        return None

    image = pygame.image.load(path).convert_alpha()

    if size:
        image = pygame.transform.smoothscale(image, size)

    return image


def draw_centered_image(surface, image, center):
    if image:
        surface.blit(image, image.get_rect(center=center))


def draw_text(surface, text, font, color, center):
    rendered = font.render(str(text), True, color)
    surface.blit(rendered, rendered.get_rect(center=center))


def game_video_rect(active=False):
    return pygame.Rect(*(ACTIVE_GAME_VIDEO_RECT if active else READY_GAME_VIDEO_RECT))


def draw_video_divider(surface, width, rect=None):
    line_x = width // 2
    video_rect = rect or game_video_rect()
    for y in range(video_rect.top, video_rect.bottom, 18):
        pygame.draw.rect(surface, (50, 255, 120), (line_x - 3, y, 6, 10))


def format_timer(total_seconds):
    total_seconds = max(0, int(total_seconds))
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02}:{seconds:02}"
