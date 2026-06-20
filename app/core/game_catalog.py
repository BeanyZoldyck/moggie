from __future__ import annotations

from dataclasses import dataclass

from app.config import MoggieConfig


@dataclass(frozen=True)
class GameDefinition:
    game_type: str
    title: str
    badge: str
    tagline: str
    accent: tuple[int, int, int]


GAMES: tuple[GameDefinition, ...] = (
    GameDefinition(
        game_type="mog_mirror",
        title="Mog Mirror",
        badge="AURA",
        tagline="Face the mirror. Claim the glow.",
        accent=(81, 238, 122),
    ),
    GameDefinition(
        game_type="sixty_seven",
        title="67 Challenge",
        badge="REP",
        tagline="Left lane, right lane, clean reps.",
        accent=(255, 203, 77),
    ),
    GameDefinition(
        game_type="emoji_face_match",
        title="Emoji Face Match",
        badge="MOJI",
        tagline="Match the face before the lane closes.",
        accent=(255, 96, 116),
    ),
)

GAME_BY_TYPE = {game.game_type: game for game in GAMES}


def game_for_type(game_type: str) -> GameDefinition:
    return GAME_BY_TYPE[game_type]


def game_index(game_type: str) -> int:
    for index, game in enumerate(GAMES):
        if game.game_type == game_type:
            return index
    return 0


def player_count_for_game(game_type: str, config: MoggieConfig) -> int:
    if game_type == "mog_mirror":
        return 2
    if game_type == "sixty_seven":
        return 1 if config.sixty_seven_mode == "solo" else 2
    if game_type == "emoji_face_match":
        return 1 if config.emoji_mode == "solo" else 2
    return 2
