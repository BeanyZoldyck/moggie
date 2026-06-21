from __future__ import annotations

from collections.abc import Mapping
from typing import Any


FEATURE_KEYS = (
    "smile",
    "mouth_open",
    "tongue_out",
    "left_eye_closed",
    "right_eye_closed",
    "eyes_closed",
    "wink",
    "neutral",
)


def classify_expression(features: dict[str, float]) -> str:
    if features.get("tongue_out", 0.0) >= 0.55 and features.get("mouth_open", 0.0) >= 0.30:
        return "tongue_out"

    left_closed = features.get("left_eye_closed", 0.0)
    right_closed = features.get("right_eye_closed", 0.0)
    if max(left_closed, right_closed, features.get("wink", 0.0)) >= 0.62 and abs(left_closed - right_closed) >= 0.25:
        return "wink"
    if max(features.get("eyes_closed", 0.0), min(left_closed, right_closed)) >= 0.62:
        return "eyes_closed"
    if features.get("mouth_open", 0.0) >= 0.72:
        return "surprised"
    if features.get("smile", 0.0) >= 0.6:
        return "smile"
    return "neutral"


def expression_matches(target_expression: str, features: Mapping[str, float] | None) -> bool:
    if features is None:
        return target_expression == "neutral"
    return classify_expression(dict(features)) == target_expression


def extract_expression_features(face: Mapping[str, Any] | None) -> dict[str, float]:
    if face is None:
        return {}
    explicit = face.get("expression_features")
    landmarks = face.get("landmarks")
    if isinstance(landmarks, Mapping):
        features = _features_from_named_landmarks(landmarks)
        if isinstance(explicit, Mapping):
            features = _merge_explicit_features(features, explicit)
        return features

    if isinstance(explicit, Mapping):
        return _normalized_features(explicit)

    return {"neutral": 1.0}


def _merge_explicit_features(features: dict[str, float], raw: Mapping[str, Any]) -> dict[str, float]:
    merged = dict(features)
    for key in FEATURE_KEYS:
        if key not in raw:
            continue
        try:
            merged[key] = _clamp(float(raw[key]))
        except (TypeError, ValueError):
            merged[key] = 0.0
    merged["eyes_closed"] = max(merged.get("eyes_closed", 0.0), min(merged["left_eye_closed"], merged["right_eye_closed"]))
    merged["wink"] = max(merged.get("wink", 0.0), abs(merged["left_eye_closed"] - merged["right_eye_closed"]))
    active = max(merged["smile"], merged["mouth_open"], merged["tongue_out"], merged["eyes_closed"], merged["wink"])
    merged["neutral"] = _clamp(1.0 - active)
    return merged


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
        active = max(features["smile"], features["mouth_open"], features["tongue_out"], features["eyes_closed"], features["wink"])
        features["neutral"] = 1.0 - active
    return features


def _features_from_named_landmarks(landmarks: Mapping[str, Any]) -> dict[str, float]:
    mouth_width = _distance(landmarks.get("mouth_left"), landmarks.get("mouth_right"))
    mouth_open = _distance(landmarks.get("upper_lip"), landmarks.get("lower_lip"))
    left_eye_open = _distance(landmarks.get("left_eye_top"), landmarks.get("left_eye_bottom"))
    right_eye_open = _distance(landmarks.get("right_eye_top"), landmarks.get("right_eye_bottom"))
    left_eye_width = _distance(landmarks.get("left_eye_outer"), landmarks.get("left_eye_inner"))
    right_eye_width = _distance(landmarks.get("right_eye_inner"), landmarks.get("right_eye_outer"))

    mouth_ratio = _ratio(mouth_open, mouth_width, default=0.0)
    mouth_open_score = _clamp((mouth_ratio - 0.10) / 0.22)
    smile_score = _smile_score(landmarks, mouth_width)
    left_closed = _eye_closed_score(left_eye_open, left_eye_width, mouth_width)
    right_closed = _eye_closed_score(right_eye_open, right_eye_width, mouth_width)
    eyes_closed = min(left_closed, right_closed)
    wink = abs(left_closed - right_closed)
    active = max(smile_score, mouth_open_score, eyes_closed, wink)
    return {
        "smile": smile_score,
        "mouth_open": mouth_open_score,
        "tongue_out": 0.0,
        "left_eye_closed": left_closed,
        "right_eye_closed": right_closed,
        "eyes_closed": eyes_closed,
        "wink": wink,
        "neutral": _clamp(1.0 - active),
    }


def _smile_score(landmarks: Mapping[str, Any], mouth_width: float) -> float:
    mouth_left = landmarks.get("mouth_left")
    mouth_right = landmarks.get("mouth_right")
    upper_lip = landmarks.get("upper_lip")
    lower_lip = landmarks.get("lower_lip")
    if mouth_width <= 0.0001 or not all(isinstance(point, Mapping) for point in (mouth_left, mouth_right, upper_lip, lower_lip)):
        return 0.0
    corner_y = (float(mouth_left["y"]) + float(mouth_right["y"])) / 2.0
    mouth_center_y = (float(upper_lip["y"]) + float(lower_lip["y"])) / 2.0
    corner_lift = (mouth_center_y - corner_y) / mouth_width
    return _clamp((corner_lift - 0.015) / 0.08)


def _eye_closed_score(eye_open: float, eye_width: float, mouth_width: float) -> float:
    reference = eye_width if eye_width > 0.0001 else mouth_width * 0.45
    openness = _ratio(eye_open, reference, default=0.2)
    return _clamp((0.17 - openness) / 0.10)


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
