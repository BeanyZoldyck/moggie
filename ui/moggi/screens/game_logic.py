from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import hypot
from random import Random
from typing import Any, Mapping


@dataclass
class SixtySevenCounter:
    reps: int = 0
    state: str = "neutral"
    min_confidence: float = 0.55
    cooldown_ms: int = 350
    stale_after_ms: int = 500
    extend_threshold: float = 0.46
    return_threshold: float = 0.26
    min_delta: float = 0.08
    last_rep_ms: int = -1_000_000
    last_distance: float | None = None
    stale: bool = False

    def reset(self):
        self.reps = 0
        self.state = "neutral"
        self.last_rep_ms = -1_000_000
        self.last_distance = None
        self.stale = False

    def update(self, hand_distance, now_ms=None):
        now = 0 if now_ms is None else now_ms
        self.stale = False
        previous = self.last_distance
        self.last_distance = hand_distance

        if previous is None:
            if hand_distance >= self.extend_threshold:
                self.state = "extended"
            return self.reps

        delta = hand_distance - previous

        if self.state == "neutral" and delta > self.min_delta:
            self.state = "extended" if hand_distance >= self.extend_threshold else "extending"
        elif self.state == "extending" and hand_distance >= self.extend_threshold:
            self.state = "extended"
        elif self.state == "extended" and delta < -self.min_delta:
            self.state = "returning"
            if hand_distance <= self.return_threshold and now - self.last_rep_ms >= self.cooldown_ms:
                self.reps += 1
                self.last_rep_ms = now
                self.state = "neutral"
        elif self.state == "returning" and hand_distance <= self.return_threshold:
            if now - self.last_rep_ms >= self.cooldown_ms:
                self.reps += 1
                self.last_rep_ms = now
            self.state = "neutral"

        return self.reps

    def update_from_hands(
        self,
        hands: list[Mapping[str, Any]],
        *,
        now_ms: int,
        frame_timestamp_ms: int | None,
        require_both_hands: bool = False,
    ):
        if frame_timestamp_ms is None or now_ms - frame_timestamp_ms > self.stale_after_ms:
            self.stale = True
            return self.reps

        self.stale = False
        usable = [
            hand
            for hand in hands
            if float(hand.get("confidence", 1.0)) >= self.min_confidence
            and isinstance(hand.get("palm_center"), Mapping)
        ]

        if require_both_hands and len(usable) < 2:
            return self.reps
        if len(usable) < 2:
            return self.reps

        return self.update(hand_distance(usable[0], usable[1]), now_ms=now_ms)


def hand_distance(first: Mapping[str, Any], second: Mapping[str, Any]):
    first_center = first["palm_center"]
    second_center = second["palm_center"]
    return hypot(
        float(first_center["x"]) - float(second_center["x"]),
        float(first_center["y"]) - float(second_center["y"]),
    )


SUPPORTED_EXPRESSIONS = ("smile", "surprised", "eyes_closed", "wink", "neutral")
EXPRESSION_LABELS = {
    "smile": "SMILE",
    "surprised": "SURPRISE",
    "eyes_closed": "EYES CLOSED",
    "wink": "WINK",
    "neutral": "DEADPAN",
}
EXPRESSION_GLYPHS = {
    "smile": ":)",
    "surprised": ":O",
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


def classify_expression(features: Mapping[str, float] | None):
    features = dict(features or {})

    if features.get("mouth_open", 0.0) >= 0.65:
        return "surprised"
    if features.get("smile", 0.0) >= 0.6:
        return "smile"

    left_closed = features.get("left_eye_closed", 0.0)
    right_closed = features.get("right_eye_closed", 0.0)

    if max(left_closed, right_closed, features.get("wink", 0.0)) >= 0.72 and abs(left_closed - right_closed) >= 0.32:
        return "wink"
    if max(features.get("eyes_closed", 0.0), min(left_closed, right_closed)) >= 0.7:
        return "eyes_closed"

    return "neutral"


def evaluate_match(target, features):
    detected = classify_expression(features)
    hit = detected == target
    return EmojiMatchResult(target=target, detected=detected, hit=hit, points=100 if hit else 0)


def build_expression_sequence(seed, count):
    rng = Random(seed)
    expressions = list(SUPPORTED_EXPRESSIONS)
    sequence = []
    previous = ""

    for _ in range(max(0, count)):
        choices = [expression for expression in expressions if expression != previous]
        picked = rng.choice(choices)
        sequence.append(picked)
        previous = picked

    return sequence


def expression_label(expression):
    return EXPRESSION_LABELS.get(expression, expression.replace("_", " ").upper())


def expression_glyph(expression):
    return EXPRESSION_GLYPHS.get(expression, "??")


def features_for_expression(expression):
    return {
        "smile": {"smile": 0.9},
        "surprised": {"mouth_open": 0.9},
        "eyes_closed": {"left_eye_closed": 0.9, "right_eye_closed": 0.9},
        "wink": {"left_eye_closed": 0.9, "right_eye_closed": 0.1},
        "neutral": {},
    }.get(expression, {})


def score_aura(*, session_id, display_name, zone, face=None, manual_override=False):
    seed = f"{session_id}:{display_name}:{zone}".encode("utf-8")
    digest = hashlib.sha256(seed).digest()
    base = 65 + digest[0] % 24
    modifier = 0

    if face is not None:
        bbox = face.get("bbox") if isinstance(face.get("bbox"), dict) else {}
        confidence = float(face.get("confidence", 0.5))
        center = face.get("center") if isinstance(face.get("center"), dict) else {}
        face_area = float(bbox.get("width", 0.0)) * float(bbox.get("height", 0.0))
        center_x = float(center.get("x", 0.25 if zone == "p1" else 0.75))
        target_x = 0.25 if zone == "p1" else 0.75
        modifier += int(max(0.0, min(1.0, confidence)) * 6)
        modifier += min(5, int(face_area * 70))
        modifier += max(0, 4 - int(abs(center_x - target_x) * 18))
    elif manual_override:
        modifier += 2
    else:
        modifier -= 5

    return max(42, min(99, base + modifier))


def winner_from_scores(player_one_score, player_two_score):
    if player_one_score > player_two_score:
        return "player_one"
    if player_two_score > player_one_score:
        return "player_two"
    return "tie"
