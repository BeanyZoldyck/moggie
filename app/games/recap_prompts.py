from __future__ import annotations

from typing import Any


RECAP_NEGATIVE_PROMPT = (
    "distorted faces, deformed features, extra people, warped anatomy, blurry, low quality, "
    "identity change, different people, text artifacts, glitch, watermark"
)


def build_recap_prompt(game_type: str, rows: list[dict[str, Any]] | None) -> str:
    """Return a result-aware image-to-video prompt for any game's recap clip.

    The source image is always the full camera frame captured at the end of the
    round (both players visible side-by-side when versus mode).
    """
    rows = rows or []
    if game_type == "mog_mirror":
        return _mog_mirror_prompt(rows)
    if game_type == "sixty_seven":
        return _sixty_seven_prompt(rows)
    if game_type == "emoji_face_match":
        return _emoji_prompt(rows)
    return _generic_prompt(rows)


def _mog_mirror_prompt(rows: list[dict[str, Any]]) -> str:
    intro = (
        "Cinematic instant-replay of a head-to-head 'Mog Mirror' face-off between two people "
        "shown side by side. "
    )
    style = (
        "Sports-highlight energy, slow-motion glow-up, dramatic scoreboard vibes, "
        "glossy and over-the-top. Keep both people clearly recognizable."
    )
    winners = [r for r in rows if r.get("winner")]
    if len(rows) >= 2 and len(winners) == 1:
        w = winners[0]
        loser = next((r for r in rows if r is not w), None)
        result = (
            f"{w.get('display_name', 'The winner')} wins with a {w.get('score', '?')} "
            f"mog score and the {w.get('label', 'mog')} aura"
        )
        if loser is not None:
            result += f", defeating {loser.get('display_name', 'the rival')} ({loser.get('score', '?')})"
        result += "."
    elif rows and len(winners) >= 2:
        result = "It's a dead-even tie — both sides equally mogged."
    else:
        result = "Two rivals trade mog energy in a close battle."
    return intro + result + " " + style


def _sixty_seven_prompt(rows: list[dict[str, Any]]) -> str:
    intro = (
        "Viral sports-recap clip of a chaotic arcade '67 Challenge' shoulder-tap battle. "
        "Both players visible side by side, performing rapid shoulder taps with hand-tracking "
        "neon overlays lighting up every rep. "
    )
    scores = _score_line(rows, unit="reps")
    winners = [r for r in rows if r.get("winner") or (len(rows) == 1)]
    if winners:
        w = winners[0]
        result = (
            f"{w.get('display_name', 'The winner')} wins with {w.get('score', '?')} reps"
            f" — {w.get('label', '67 CERTIFIED')}."
        )
    else:
        result = f"Final scores: {scores}."
    style = (
        "High-energy sports broadcast feel: speed ramps, impact flashes, crowd hype, "
        "exaggerated rep-count ticker, slow-motion winner reveal. Loud and playful."
    )
    return intro + result + " " + style


def _emoji_prompt(rows: list[dict[str, Any]]) -> str:
    intro = (
        "Viral arcade recap of an Emoji Face Match battle — players pulling extreme "
        "expressions (smiles, surprise, tongue-out) as emoji targets fly across the screen. "
    )
    hits_line = _hits_line(rows)
    winners = [r for r in rows if r.get("winner") or (len(rows) == 1)]
    if winners:
        w = winners[0]
        result = (
            f"{w.get('display_name', 'The winner')} wins — {w.get('label', 'MOJI FINAL BOSS')} "
            f"with {w.get('score', '?')} points."
        )
    else:
        result = f"Final results: {hits_line}."
    style = (
        "Fast, meme-ready editing: dramatic face zooms, emoji explosion effects, "
        "reaction cuts, streak counter pop, and a celebratory winner beat. "
        "Expressive and funny."
    )
    return intro + result + " " + style


def _generic_prompt(rows: list[dict[str, Any]]) -> str:
    scores = _score_line(rows)
    return (
        f"Dramatic arcade game recap. Players visible in frame. Final scores: {scores}. "
        "Cinematic highlight reel with energy, winner reveal, and celebration. "
        "Glossy, playful, over-the-top."
    )


def _score_line(rows: list[dict[str, Any]], unit: str = "pts") -> str:
    parts = [f"{r.get('display_name', '?')}: {r.get('score', '?')} {unit}" for r in rows]
    return ", ".join(parts) if parts else "no scores"


def _hits_line(rows: list[dict[str, Any]]) -> str:
    parts = [
        f"{r.get('display_name', '?')}: {r.get('score', '?')} pts"
        for r in rows
    ]
    return ", ".join(parts) if parts else "no results"
