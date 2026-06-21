from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Callable, Mapping

from app.cv.expression_features import classify_expression


SUPPORTED_EXPRESSIONS = ("smile", "surprised", "tongue_out", "neutral", "look_left", "look_right")
EXPRESSION_LABELS = {
    "smile": "SMILE",
    "surprised": "SURPRISE",
    "tongue_out": "TONGUE OUT",
    "neutral": "DEADPAN",
    "look_left": "LOOK LEFT",
    "look_right": "LOOK RIGHT",
}
EXPRESSION_GLYPHS = {
    "smile": ":)",
    "surprised": ":O",
    "tongue_out": ":P",
    "neutral": ":|",
    "look_left": "L",
    "look_right": "R",
}

ExpressionPredicate = Callable[[Mapping[str, float]], bool]


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
    normalized = dict(features or {})
    detected = classify_expression(normalized)
    hit = EXPRESSION_PREDICATES.get(target, _target_unknown)(normalized)
    return EmojiMatchResult(target=target, detected=detected, hit=hit, points=100 if hit else 0)


def _target_smile(features: Mapping[str, float]) -> bool:
    return features.get("smile", 0.0) >= 0.55


def _target_surprised(features: Mapping[str, float]) -> bool:
    return features.get("mouth_open", 0.0) >= 0.70


def _target_tongue_out(features: Mapping[str, float]) -> bool:
    return features.get("tongue_out", 0.0) >= 0.42 and features.get("mouth_open", 0.0) >= 0.20


def _target_look_left(features: Mapping[str, float]) -> bool:
    return features.get("look_left", 0.0) >= 0.60


def _target_look_right(features: Mapping[str, float]) -> bool:
    return features.get("look_right", 0.0) >= 0.60


def _target_neutral(features: Mapping[str, float]) -> bool:
    active = max(
        features.get("smile", 0.0),
        features.get("mouth_open", 0.0),
        features.get("tongue_out", 0.0),
        features.get("wink", 0.0),
        features.get("look_left", 0.0),
        features.get("look_right", 0.0),
    )
    return active < 0.45


def _target_unknown(_: Mapping[str, float]) -> bool:
    return False


EXPRESSION_PREDICATES: dict[str, ExpressionPredicate] = {
    "smile": _target_smile,
    "surprised": _target_surprised,
    "tongue_out": _target_tongue_out,
    "neutral": _target_neutral,
    "look_left": _target_look_left,
    "look_right": _target_look_right,
}


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
