from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Mapping

from app.cv.expression_features import classify_expression


SUPPORTED_EXPRESSIONS = ("smile", "surprised", "tongue_out", "eyes_closed", "wink", "neutral")
EXPRESSION_LABELS = {
    "smile": "SMILE",
    "surprised": "SURPRISE",
    "tongue_out": "TONGUE OUT",
    "eyes_closed": "EYES CLOSED",
    "wink": "WINK",
    "neutral": "DEADPAN",
}
EXPRESSION_GLYPHS = {
    "smile": ":)",
    "surprised": ":O",
    "tongue_out": ":P",
    "eyes_closed": "-_-",
    "wink": ";)",
    "neutral": ":|",
}


@dataclass(frozen=True)
class EmojiMatchResult:
    target: str
    detected: str
    hit: bool
    points: int


class EmojiFaceMatchGame:
    game_type = "emoji_face_match"
    min_players = 1
    max_players = 2


def expression_label(expression: str) -> str:
    return EXPRESSION_LABELS.get(expression, expression.replace("_", " ").upper())


def expression_glyph(expression: str) -> str:
    return EXPRESSION_GLYPHS.get(expression, "??")


def evaluate_match(target: str, features: Mapping[str, float] | None) -> EmojiMatchResult:
    detected = classify_expression(dict(features or {}))
    hit = detected == target
    return EmojiMatchResult(target=target, detected=detected, hit=hit, points=100 if hit else 0)


def build_expression_sequence(seed: str, count: int) -> list[str]:
    rng = Random(seed)
    expressions = list(SUPPORTED_EXPRESSIONS)
    sequence: list[str] = []
    previous = ""
    for _ in range(max(0, count)):
        choices = [expression for expression in expressions if expression != previous]
        picked = rng.choice(choices)
        sequence.append(picked)
        previous = picked
    return sequence


def label_for_score(score: int, *, winner: bool, hits: int, attempts: int) -> str:
    if attempts == 0:
        return "NO MOJIS"
    accuracy = hits / attempts
    if winner and accuracy >= 0.8:
        return "MOJI FINAL BOSS"
    if winner:
        return "FACE MATCH CHAMP"
    if accuracy >= 0.65:
        return "CLEAN EXPRESSIONS"
    if hits > 0:
        return "REACTION READY"
    return "STONE FACE"
