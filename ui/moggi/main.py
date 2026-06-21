import os

import pygame

from screens.camera_cv import CameraCVBridge
from screens.emoji_match import EmojiMatchScreen
from screens.menu import MenuScreen
from screens.mog_mirror import MogMirrorScreen
from screens.sixseven import SixSevenScreen
from screens.win import WinScreen


WIDTH = 1280
HEIGHT = 720


def main():
    pygame.init()
    pygame.display.set_caption("MOGGI Arcade")

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    camera_index = int(os.environ.get("MOGGI_CAMERA_INDEX", "0"))
    camera = CameraCVBridge(camera_index=camera_index)
    camera.start()

    menu_screen = MenuScreen(WIDTH, HEIGHT)
    win_screen = WinScreen(WIDTH, HEIGHT)
    game_screens = {
        "sixseven": SixSevenScreen(WIDTH, HEIGHT),
        "mogmirror": MogMirrorScreen(WIDTH, HEIGHT),
        "emoji": EmojiMatchScreen(WIDTH, HEIGHT),
    }

    current_screen = "menu"
    active_game = None
    latest_result = {
        "winner": "tie",
        "player_one_score": 0,
        "player_two_score": 0,
    }

    running = True

    while running:
        dt = clock.tick(60)
        camera.poll()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue

            if current_screen == "menu":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                else:
                    menu_screen.handle_event(event)

            elif current_screen == "win":
                action = win_screen.handle_event(event)
                if action == "menu":
                    if active_game:
                        game_screens[active_game].reset()
                    menu_screen.reset()
                    current_screen = "menu"
                elif action == "replay" and active_game:
                    game_screens[active_game].reset()
                    current_screen = active_game

            else:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    game_screens[current_screen].reset()
                    menu_screen.reset()
                    current_screen = "menu"
                else:
                    game_screens[current_screen].handle_event(event)

        if current_screen == "menu":
            menu_screen.update(dt)
            if menu_screen.start_game:
                active_game = menu_screen.consume_start_game()
                game_screens[active_game].reset()
                current_screen = active_game

        elif current_screen == "win":
            pass

        else:
            game_screen = game_screens[current_screen]
            if hasattr(game_screen, "update_cv"):
                game_screen.update_cv(camera)
            game_screen.update(dt)

            if game_screen.exit_to_menu:
                game_screen.reset()
                menu_screen.reset()
                current_screen = "menu"
            elif game_screen.finished:
                latest_result = game_screen.get_result()
                current_screen = "win"

        if current_screen == "menu":
            menu_screen.draw(screen)
        elif current_screen == "win":
            win_screen.draw(
                screen,
                latest_result["winner"],
                latest_result["player_one_score"],
                latest_result["player_two_score"],
            )
        else:
            game_screens[current_screen].draw(screen, camera)

        pygame.display.flip()

    camera.stop()
    pygame.quit()


if __name__ == "__main__":
    main()
