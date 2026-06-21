from __future__ import annotations

import random

GameMoment = str

MOG_MIRROR_INTRO = [
    "Step into the mirror lane!",
    "Face off! Mog Mirror is live!",
    "Two players. One mirror. Let's go!",
    "Show me that arcade aura!",
]

MOG_MIRROR_END = [
    "Brutal!",
    "Savage mirror match!",
    "That aura was illegal!",
    "Mirror certified chaos!",
    "Unreal face energy!",
    "The crowd goes wild!",
    "Next level mogging!",
]

SIXTY_SEVEN_INTRO = [
    "Six seven challenge! Pump those reps!",
    "Hands up! Let's count those sevens!",
    "Rep city! Make it nasty!",
    "Arcade reps on the board!",
]

SIXTY_SEVEN_END = [
    "Rep master!",
    "Certified six seven!",
    "Hands were on fire!",
    "That was filthy!",
    "Arcade athlete confirmed!",
    "Unreal rep speed!",
]

EMOJI_INTRO = [
    "Emoji face match! Hit those expressions!",
    "Make that face! Score those points!",
    "Reaction time showdown!",
    "Meme face battle begins!",
]

EMOJI_END = [
    "Emoji legend!",
    "Face game unmatched!",
    "That reaction was nasty!",
    "Meme machine activated!",
    "Expression overload!",
    "Arcade emoji champion!",
]

_LINES: dict[tuple[str, GameMoment], list[str]] = {
    ("mog_mirror", "intro"): MOG_MIRROR_INTRO,
    ("mog_mirror", "end"): MOG_MIRROR_END,
    ("sixty_seven", "intro"): SIXTY_SEVEN_INTRO,
    ("sixty_seven", "end"): SIXTY_SEVEN_END,
    ("emoji_face_match", "intro"): EMOJI_INTRO,
    ("emoji_face_match", "end"): EMOJI_END,
}


def pick_voiceline(game_type: str, moment: GameMoment) -> str:
    pool = _LINES.get((game_type, moment))
    if not pool:
        return ""
    return random.choice(pool)
