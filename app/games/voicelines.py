from __future__ import annotations

import random

GameMoment = str

MOG_MIRROR_INTRO = [
    "Welcome to Mog Mirror! Light it up!",
    "Face off! Mog Mirror is live!",
    "Two players, one mirror, zero mercy!",
    "Step into the lane and bring the heat!",
    "Arcade aura check! Let's go!",
    "Mirror match! Show me something nasty!",
    "Center up! This mirror don't lie!",
    "It's mogging time! Let's ride!",
    "Neon mirror showdown! Hit it!",
    "Players ready? Mog Mirror engaged!",
    "Hold that pose! The mirror is watching!",
    "Lane split! Who's got the aura?",
]

MOG_MIRROR_END = [
    "Brutal!",
    "Savage mirror match!",
    "That aura was illegal!",
    "Mirror certified chaos!",
    "Unreal face energy!",
    "The crowd goes wild!",
    "Next level mogging!",
    "Absolutely cooked!",
    "Face game on ten!",
    "Mirror said no survivors!",
    "That was disrespectful!",
    "Aura overload! What a finish!",
    "Mogged into another dimension!",
    "The mirror is still shaking!",
    "Certified arcade menace!",
    "Too much sauce on that one!",
]

SIXTY_SEVEN_INTRO = [
    "Six seven challenge! Pump those reps!",
    "Hands up! Count those sevens!",
    "Rep city! Make it nasty!",
    "Arcade reps on the board!",
    "Six seven time! Move those hands!",
    "Speed reps! Let's get chaotic!",
    "Hand tracking locked! Go go go!",
    "Rep battle engaged! No breaks!",
    "Show me those sevens! Fast!",
    "Arcade athlete mode activated!",
    "Hands in frame! Rep season!",
    "Six seven hype train leaving now!",
]

SIXTY_SEVEN_END = [
    "Rep master!",
    "Certified six seven!",
    "Hands were on fire!",
    "That was filthy!",
    "Arcade athlete confirmed!",
    "Unreal rep speed!",
    "Rep count went crazy!",
    "Finger fireworks!",
    "Six seven legend status!",
    "Hands don't miss!",
    "Rep machine unlocked!",
    "That pace was nasty!",
    "Arcade gym rat energy!",
    "Too many reps! Too much heat!",
    "Six seven champion!",
]

EMOJI_INTRO = [
    "Emoji face match! Hit those expressions!",
    "Make that face! Score those points!",
    "Reaction time showdown!",
    "Meme face battle begins!",
    "Emoji chaos starts now!",
    "Face check! Match that mood!",
    "Expression sprint! Go go go!",
    "Meme lane open! Hit the targets!",
    "Emoji reflex test! Don't blink!",
    "Face game loaded! Let's cook!",
    "Reaction royale! Show the face!",
    "Emoji arcade! Match or miss!",
]

EMOJI_END = [
    "Emoji legend!",
    "Face game unmatched!",
    "That reaction was nasty!",
    "Meme machine activated!",
    "Expression overload!",
    "Arcade emoji champion!",
    "Face speed demon!",
    "Meme reflex god tier!",
    "Emoji points through the roof!",
    "That face hit different!",
    "Reaction time criminal!",
    "Expression on max volume!",
    "Meme lord confirmed!",
    "Emoji board exploded!",
    "Face match complete! What a run!",
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
