from __future__ import annotations


def classify_expression(features: dict[str, float]) -> str:
    if features.get("mouth_open", 0.0) > 0.65:
        return "surprised"
    if features.get("smile", 0.0) > 0.6:
        return "smile"
    if features.get("eyes_closed", 0.0) > 0.7:
        return "eyes_closed"
    if features.get("wink", 0.0) > 0.7:
        return "wink"
    return "neutral"
