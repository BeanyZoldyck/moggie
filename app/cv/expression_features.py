from __future__ import annotations

from collections.abc import Mapping
from typing import Any


FEATURE_KEYS = (
    "smile",
    "mouth_open",
    "left_eye_closed",
    "right_eye_closed",
    "eyes_closed",
    "wink",
    "neutral",
)


def classify_expression(features: dict[str, float]) -> str:
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


def expression_matches(target_expression: str, features: Mapping[str, float] | None) -> bool:
    if features is None:
        return target_expression == "neutral"
    return classify_expression(dict(features)) == target_expression


def extract_expression_features(face: Mapping[str, Any] | None) -> dict[str, float]:
    if face is None:
        return {}
    explicit = face.get("expression_features")
    if isinstance(explicit, Mapping):
        return _normalized_features(explicit)

    landmarks = face.get("landmarks")
    if isinstance(landmarks, Mapping):
        return _features_from_named_landmarks(landmarks)

    return {"neutral": 1.0}


def _normalized_features(raw: Mapping[str, Any]) -> dict[str, float]:
    features: dict[str, float] = {}
    for key in FEATURE_KEYS:
        try:
            features[key] = _clamp(float(raw.get(key, 0.0)))
        except (TypeError, ValueError):
            features[key] = 0.0
    if "eyes_closed" not in raw:
        features["eyes_closed"] = min(features["left_eye_closed"], features["right_eye_closed"])
    if "wink" not in raw:
        features["wink"] = max(0.0, abs(features["left_eye_closed"] - features["right_eye_closed"]))
    if "neutral" not in raw:
        active = max(features["smile"], features["mouth_open"], features["eyes_closed"], features["wink"])
        features["neutral"] = 1.0 - active
    return features


def _features_from_named_landmarks(landmarks: Mapping[str, Any]) -> dict[str, float]:
    mouth_width = _distance(landmarks.get("mouth_left"), landmarks.get("mouth_right"))
    mouth_open = _distance(landmarks.get("upper_lip"), landmarks.get("lower_lip"))
    left_eye_open = _distance(landmarks.get("left_eye_top"), landmarks.get("left_eye_bottom"))
    right_eye_open = _distance(landmarks.get("right_eye_top"), landmarks.get("right_eye_bottom"))

    smile = _ratio(mouth_width, mouth_open, default=0.0)
    smile_score = _clamp((smile - 4.2) / 2.0)
    mouth_open_score = _clamp(_ratio(mouth_open, mouth_width, default=0.0) * 5.0)
    left_closed = _clamp(1.0 - _ratio(left_eye_open, mouth_width, default=0.05) * 18.0)
    right_closed = _clamp(1.0 - _ratio(right_eye_open, mouth_width, default=0.05) * 18.0)
    eyes_closed = min(left_closed, right_closed)
    wink = abs(left_closed - right_closed)
    active = max(smile_score, mouth_open_score, eyes_closed, wink)
    return {
        "smile": smile_score,
        "mouth_open": mouth_open_score,
        "left_eye_closed": left_closed,
        "right_eye_closed": right_closed,
        "eyes_closed": eyes_closed,
        "wink": wink,
        "neutral": 1.0 - active,
    }


def _distance(a: Any, b: Any) -> float:
    if not isinstance(a, Mapping) or not isinstance(b, Mapping):
        return 0.0
    try:
        ax = float(a["x"])
        ay = float(a["y"])
        bx = float(b["x"])
        by = float(b["y"])
    except (KeyError, TypeError, ValueError):
        return 0.0
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _ratio(numerator: float, denominator: float, *, default: float) -> float:
    if denominator <= 0.0001:
        return default
    return numerator / denominator


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
