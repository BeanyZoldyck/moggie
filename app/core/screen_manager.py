from __future__ import annotations


class ScreenManager:
    def __init__(self, initial_screen: str = "home") -> None:
        self.current_screen = initial_screen

    def go_to(self, screen_name: str) -> None:
        self.current_screen = screen_name
