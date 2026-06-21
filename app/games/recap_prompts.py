from __future__ import annotations

from typing import Any

# Keep faces clean — the hammy energy comes from the scene, not distortion.
RECAP_NEGATIVE_PROMPT = (
    "distorted faces, morphed identity, warped anatomy, body horror, extra limbs, "
    "blurry faces, low quality, watermark, text overlay errors, realistic gore"
)


def build_recap_prompt(game_type: str, rows: list[dict[str, Any]] | None) -> str:
    """Return a result-aware, bowling-alley-hammy image-to-video prompt.

    Source image: full camera frame at round end, both players visible.
    Goal: treat the completely mundane as a cosmos-shaking event.
    """
    rows = rows or []
    if game_type == "mog_mirror":
        return _mog_mirror_prompt(rows)
    if game_type == "sixty_seven":
        return _sixty_seven_prompt(rows)
    if game_type == "emoji_face_match":
        return _emoji_prompt(rows)
    return _generic_prompt(rows)


# ---------------------------------------------------------------------------
# Mog Mirror
# ---------------------------------------------------------------------------

def _mog_mirror_prompt(rows: list[dict[str, Any]]) -> str:
    winners = [r for r in rows if r.get("winner")]
    losers = [r for r in rows if not r.get("winner")]

    if len(rows) >= 2 and len(winners) == 1:
        w, lo = winners[0], losers[0] if losers else None
        w_name = w.get("display_name", "The winner")
        w_score = w.get("score", "?")
        w_label = w.get("label", "MIRROR VERIFIED")
        lo_name = lo.get("display_name", "the rival") if lo else None
        lo_score = lo.get("score", "?") if lo else None

        # Pick a celebration register based on the label
        if w_label in {"BOOTH FINAL BOSS"}:
            winner_beat = (
                f"A single divine golden beam of light slams down from above onto {w_name}'s face. "
                "Their skin slowly begins to glow, their jawline sharpens frame by frame, "
                "their eyes catch a supernatural hunter glint. "
                "The camera pushes in slowly — reverential, almost afraid. "
                "Neon aura rings orbit their head. Confetti in gold and green erupts from both sides. "
                "Giant embossed championship text crashes in from off-screen in slow motion. "
            )
        elif w_label in {"MIRROR VERIFIED"}:
            winner_beat = (
                f"Dramatic slow push-in on {w_name}'s face as a warm golden spotlight materialises around them. "
                "Soft lens flares streak across the frame. "
                "Their side of the screen blooms with soft neon light while a shimmer ripple passes over them "
                "like a mirror being polished. Confetti drifts down. "
            )
        else:
            winner_beat = (
                f"The camera drifts slowly toward {w_name} as a single spotlight finds them. "
                "A gentle sparkle effect cascades over their face. Subtle confetti falls. "
            )

        if lo_name:
            loser_beat = (
                f"Meanwhile {lo_name} (score {lo_score}) gets a brief sad spotlight — "
                "a single small cloud appears above their head, rains for exactly one second, then stops. "
                "They look fine. They are fine. They are not fine. "
            )
        else:
            loser_beat = ""

        close = (
            "End on a freeze-frame of both faces side by side with a cheesy arcade scoreboard graphic "
            f"reading {w_score} vs {lo_score if lo_score else '?'}. "
            "The whole thing has the energy of a bowling alley strike video at 11pm on a Tuesday. "
            "Hammy, sincere, deeply committed to the bit."
        )
        return winner_beat + loser_beat + close

    elif rows and len(winners) >= 2:
        # Tie
        names = " and ".join(r.get("display_name", "Player") for r in rows[:2])
        return (
            f"Both {names} are bathed simultaneously in twin pillars of golden light from above. "
            "The camera pulls back slowly to reveal confetti cannons firing on both sides at once. "
            "Both faces are surrounded by identical neon aura rings that pulse in sync. "
            "A dramatic orchestral sting. The scoreboard graphic shows equal scores with twin trophy icons. "
            "The energy: two people who both won the bowling league championship at the exact same moment. "
            "Glorious, ridiculous, completely earned."
        )
    else:
        # Single player or no clear result
        name = rows[0].get("display_name", "The player") if rows else "The player"
        score = rows[0].get("score", "?") if rows else "?"
        return (
            f"Slow dramatic push-in on {name}'s face as a golden spotlight descends. "
            f"The score — {score} — floats up in glowing arcade numerals. "
            "Confetti. Lens flare. The camera orbits slowly. "
            "The energy of a bowling alley when someone gets a spare and the whole system loses its mind anyway."
        )


# ---------------------------------------------------------------------------
# 67 Challenge
# ---------------------------------------------------------------------------

def _sixty_seven_prompt(rows: list[dict[str, Any]]) -> str:
    winners = [r for r in rows if r.get("winner") or len(rows) == 1]
    losers = [r for r in rows if not r.get("winner") and len(rows) > 1]
    solo = len(rows) == 1

    if winners:
        w = winners[0]
        w_name = w.get("display_name", "The winner")
        w_score = w.get("score", 0)
        w_label = w.get("label", "67 CERTIFIED")

        if isinstance(w_score, int) and w_score >= 50:
            scale = "legendary"
            effect = (
                "Each shoulder-tap sends a visible shockwave rippling through the air. "
                "Neon lightning arcs off their arms on every rep. "
                "A giant holographic rep counter slams up like a fruit machine hitting jackpot. "
            )
        elif isinstance(w_score, int) and w_score >= 20:
            scale = "impressive"
            effect = (
                "The shoulder-taps go to dramatic slow-motion — each one lands like a heavyweight punch. "
                "A glowing rep counter ticker climbs in real time. "
                "Spotlights sweep across them. "
            )
        else:
            scale = "valid and celebrated"
            effect = (
                "A single spotlight finds them. The rep count floats up in glowing numerals. "
                "Confetti drifts down. Small but sincere."
            )

        if solo:
            setup = (
                f"The camera starts wide, then slowly pushes in on {w_name} mid-tap. "
                f"The final score of {w_score} reps hangs in the air like a verdict from the gods. "
            )
            crowd = (
                "The energy: a solo bowler who just got a perfect 300 at midnight and the machine "
                "plays the full celebration anyway for an empty lane."
            )
        else:
            lo = losers[0] if losers else None
            lo_name = lo.get("display_name", "the opponent") if lo else "the opponent"
            lo_score = lo.get("score", "?") if lo else "?"
            setup = (
                f"Slow-motion freeze on {w_name}'s winning shoulder-tap — the decisive rep. "
                f"Final score: {w_score} vs {lo_score}. "
                f"{lo_name} gets a respectful nod graphic. They tried. It was close-ish. "
            )
            crowd = (
                "The energy: a bowling alley strike video where the winner is treated like they just "
                "won a world championship and everyone in the building knows it."
            )

        return (
            "Video style: cheesy arcade sports replay, neon-lit, late-90s aesthetic, sincere commitment to the drama. "
            + setup + effect
            + f"Giant embossed text reads '{w_label}'. "
            + crowd
        )

    # Fallback
    scores = ", ".join(f"{r.get('display_name','?')}: {r.get('score','?')}" for r in rows)
    return (
        "Arcade sports replay of a 67 Challenge battle. "
        f"Final rep counts: {scores}. "
        "Slow-motion shoulder taps, neon impact flashes, glowing scoreboard. "
        "The energy of a bowling alley celebration that goes slightly too hard for the situation. "
        "Hammy, joyful, neon-lit."
    )


# ---------------------------------------------------------------------------
# Emoji Face Match
# ---------------------------------------------------------------------------

def _emoji_prompt(rows: list[dict[str, Any]]) -> str:
    winners = [r for r in rows if r.get("winner") or len(rows) == 1]
    losers = [r for r in rows if not r.get("winner") and len(rows) > 1]
    solo = len(rows) == 1

    if winners:
        w = winners[0]
        w_name = w.get("display_name", "The winner")
        w_score = w.get("score", 0)
        w_label = w.get("label", "MOJI FINAL BOSS")

        if w_label == "MOJI FINAL BOSS":
            peak = (
                f"The camera slams in on {w_name}'s face in extreme close-up. "
                "A cascade of giant emoji explodes out from behind them — smileys, stars, fire — "
                "filling the whole background. Their expression is frozen in perfect form like a statue. "
                "Golden light beams radiate outward. The screen fills with confetti. "
                "A trophy materialises in their hands from nowhere."
            )
        elif w_label in {"REACTION READY", "STONE FACE"}:
            peak = (
                f"Slow push-in on {w_name}'s face. A single giant emoji floats up and locks into place "
                "next to them like a match confirmed. Spotlight, sparkle, polite confetti."
            )
        else:
            peak = (
                f"The camera finds {w_name} and holds on their expression. "
                "Emoji float up and orbit their face. A score graphic flashes. Confetti falls."
            )

        if solo:
            context = (
                f"Final score: {w_score} points. Solo run. "
                "The machine celebrates anyway, hard. "
                "The energy: a bowling alley where you bowl alone at 1am and still get the full ceremony."
            )
        else:
            lo = losers[0] if losers else None
            lo_name = lo.get("display_name", "the rival") if lo else "the rival"
            lo_score = lo.get("score", "?") if lo else "?"
            context = (
                f"Scoreboard shows {w_score} vs {lo_score}. "
                f"{lo_name} gets a tiny sad emoji (one tear, one second, tasteful). "
                "The energy: a bowling alley where someone gets a strike and the system just completely "
                "loses all composure — fog machines, lasers, the works."
            )

        return (
            "Video style: instant bowling-alley celebration mode, full commitment, "
            "neon and garish and deeply sincere. "
            + peak + " " + context
        )

    # Fallback
    scores = ", ".join(f"{r.get('display_name','?')}: {r.get('score','?')}" for r in rows)
    return (
        "Arcade recap of an Emoji Face Match. "
        f"Results: {scores}. "
        "Giant emoji explode across the screen. Faces get dramatic close-ups. "
        "Confetti, spotlights, a scoreboard. "
        "Bowling-alley celebration energy: completely over the top for the situation, and perfect for it."
    )


# ---------------------------------------------------------------------------
# Generic fallback
# ---------------------------------------------------------------------------

def _generic_prompt(rows: list[dict[str, Any]]) -> str:
    scores = ", ".join(f"{r.get('display_name','?')}: {r.get('score','?')}" for r in rows)
    return (
        "Instant arcade celebration video. "
        f"Players in frame. Final scores: {scores}. "
        "Dramatic slow push-in. Confetti cannon fires. Golden spotlight descends. "
        "Giant glowing score graphic. Freeze frame. "
        "The energy of a bowling alley strike video at maximum sincerity — "
        "completely committed to celebrating something that maybe didn't need this much ceremony, "
        "and all the better for it."
    )
