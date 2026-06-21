from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import hypot
from typing import Any, Mapping


@dataclass(frozen=True)
class MogMirrorResult:
    display_name: str
    zone: str
    score: int
    label: str
    crop_bgr: Any | None
    face: dict[str, Any] | None
    ai_job_ids: list[str]


class MogMirrorGame:
    game_type = "mog_mirror"
    min_players = 2
    max_players = 2


# Prompt for the start-of-game "mog avatar" image-to-video pass (fal.ai Pika).
MOG_AVATAR_PROMPT = (
    "Transform this person into their most 'mogged' version: a chiseled, razor-sharp jawline, "
    "intense hunter eyes with a confident slight squint, flawless facial symmetry and ideal "
    "facial thirds, high cheekbones and clean skin, hyper-attractive and cinematic. Keep their "
    "identity clearly recognizable as the same person. Subtle confident head movement, looking "
    "straight at the camera, dramatic studio lighting."
)
MOG_AVATAR_NEGATIVE_PROMPT = (
    "distorted face, deformed features, extra faces, multiple people, warped jaw, asymmetric, "
    "blurry, low quality, identity change, different person, cartoon, disfigured, glitch"
)


def score_aura(
    *,
    session_id: str,
    display_name: str,
    zone: str,
    face: dict[str, Any] | None,
    manual_override: bool = False,
    sample_ms: int | None = None,
) -> int:
    sample_bucket = "" if sample_ms is None else f":{sample_ms // 500}"
    seed = f"{session_id}:{display_name}:{zone}{sample_bucket}".encode("utf-8")
    digest = hashlib.sha256(seed).digest()
    base = 38 + digest[0] % 28
    modifier = 0
    if face is not None:
        bbox = face.get("bbox") if isinstance(face.get("bbox"), dict) else {}
        confidence = float(face.get("confidence", 0.5))
        center = face.get("center") if isinstance(face.get("center"), dict) else {}
        face_area = float(bbox.get("width", 0.0)) * float(bbox.get("height", 0.0))
        center_x = float(center.get("x", 0.25 if zone == "p1" else 0.75))
        center_y = float(center.get("y", 0.35))
        box_w = float(bbox.get("width", 0.0))
        box_h = float(bbox.get("height", 0.0))
        target_x = 0.25 if zone == "p1" else 0.75
        centered_x = max(0.0, 1.0 - abs(center_x - target_x) * 5.8)
        centered_y = max(0.0, 1.0 - abs(center_y - 0.38) * 3.4)
        modifier += int(max(0.0, min(1.0, confidence)) * 5)
        modifier += min(5, int(face_area * 70))
        modifier += int(centered_x * 5)
        modifier += int(centered_y * 3)
        modifier += int(_facial_geometry_score(face) * 20) - 13
        signature = f"{confidence:.3f}:{center_x:.3f}:{center_y:.3f}:{box_w:.3f}:{box_h:.3f}".encode("utf-8")
        face_digest = hashlib.sha256(signature + seed).digest()
        if sample_ms is None:
            modifier += face_digest[0] % 9 - 4
        else:
            jitter = face_digest[0] % 35 - 17
            surge = face_digest[1] % 11 if face_digest[2] % 4 == 0 else 0
            dip = face_digest[3] % 10 if face_digest[4] % 5 == 0 else 0
            modifier += jitter + surge - dip
    elif manual_override:
        modifier += digest[1] % 15 - 5
    else:
        modifier -= 12
    return max(25, min(100, base + modifier))


def _facial_geometry_score(face: Mapping[str, Any]) -> float:
    landmarks = face.get("landmarks")
    if not isinstance(landmarks, Mapping):
        return _bbox_geometry_score(face)

    left_eye_outer = _point(landmarks.get("left_eye_outer"))
    left_eye_inner = _point(landmarks.get("left_eye_inner"))
    right_eye_inner = _point(landmarks.get("right_eye_inner"))
    right_eye_outer = _point(landmarks.get("right_eye_outer"))
    mouth_left = _point(landmarks.get("mouth_left"))
    mouth_right = _point(landmarks.get("mouth_right"))
    nose_tip = _point(landmarks.get("nose_tip"))
    chin = _point(landmarks.get("chin"))
    left_cheek = _point(landmarks.get("left_cheek"))
    right_cheek = _point(landmarks.get("right_cheek"))

    bbox = face.get("bbox") if isinstance(face.get("bbox"), Mapping) else {}
    face_width = float(bbox.get("width", 0.0)) or _distance(left_cheek, right_cheek)
    face_height = float(bbox.get("height", 0.0)) or _distance(nose_tip, chin) * 2.0
    if face_width <= 0.0001 or face_height <= 0.0001:
        return _bbox_geometry_score(face)

    eye_center_l = _midpoint(left_eye_outer, left_eye_inner)
    eye_center_r = _midpoint(right_eye_inner, right_eye_outer)
    mouth_center = _midpoint(mouth_left, mouth_right)
    feature_mid_x = _average(
        [
            _average_x(eye_center_l, eye_center_r),
            _average_x(mouth_left, mouth_right),
            nose_tip["x"] if nose_tip else None,
            chin["x"] if chin else None,
        ]
    )

    symmetry_errors = [
        abs(_distance_x(left_eye_outer, feature_mid_x) - _distance_x(right_eye_outer, feature_mid_x)) / face_width,
        abs(_distance_x(left_eye_inner, feature_mid_x) - _distance_x(right_eye_inner, feature_mid_x)) / face_width,
        abs(_distance_x(mouth_left, feature_mid_x) - _distance_x(mouth_right, feature_mid_x)) / face_width,
        abs((nose_tip["x"] - feature_mid_x) / face_width) if nose_tip else 0.18,
        abs((chin["x"] - feature_mid_x) / face_width) if chin else 0.18,
    ]
    symmetry = _clamp(1.0 - _average(symmetry_errors) * 5.2)

    eye_gap = _distance(right_eye_inner, left_eye_inner)
    outer_eye_width = _distance(right_eye_outer, left_eye_outer)
    eye_spacing_ratio = eye_gap / face_width if face_width > 0.0 else 0.0
    eye_band_ratio = outer_eye_width / face_width if face_width > 0.0 else 0.0
    eye_spacing = _clamp(1.0 - abs(eye_spacing_ratio - 0.28) * 5.8)
    eye_balance = _clamp(1.0 - abs(eye_band_ratio - 0.70) * 2.6)

    jawline = _jawline_score(chin, left_cheek, right_cheek, mouth_center, face_width, face_height)
    return _clamp(symmetry * 0.42 + jawline * 0.30 + eye_spacing * 0.20 + eye_balance * 0.08)


def _bbox_geometry_score(face: Mapping[str, Any]) -> float:
    bbox = face.get("bbox") if isinstance(face.get("bbox"), Mapping) else {}
    width = float(bbox.get("width", 0.0))
    height = float(bbox.get("height", 0.0))
    if width <= 0.0001 or height <= 0.0001:
        return 0.38
    aspect = width / height
    sharpness = _clamp(1.0 - abs(aspect - 0.66) * 2.4)
    size = _clamp((width * height - 0.018) / 0.055)
    return _clamp(sharpness * 0.65 + size * 0.35)


def _jawline_score(
    chin: Mapping[str, float] | None,
    left_cheek: Mapping[str, float] | None,
    right_cheek: Mapping[str, float] | None,
    mouth_center: Mapping[str, float] | None,
    face_width: float,
    face_height: float,
) -> float:
    if chin is None or left_cheek is None or right_cheek is None:
        return 0.46
    jaw_width = _distance(left_cheek, right_cheek)
    taper = jaw_width / face_width if face_width > 0.0 else 0.0
    chin_drop = (chin["y"] - mouth_center["y"]) / face_height if mouth_center is not None and face_height > 0.0 else 0.0
    sharp_taper = _clamp(1.0 - abs(taper - 0.84) * 2.8)
    sharp_chin = _clamp(1.0 - abs(chin_drop - 0.31) * 5.0)
    return _clamp(sharp_taper * 0.45 + sharp_chin * 0.55)


def _point(value: Any) -> Mapping[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        return {"x": float(value["x"]), "y": float(value["y"])}
    except (KeyError, TypeError, ValueError):
        return None


def _midpoint(first: Mapping[str, float] | None, second: Mapping[str, float] | None) -> Mapping[str, float] | None:
    if first is None or second is None:
        return None
    return {"x": (first["x"] + second["x"]) / 2.0, "y": (first["y"] + second["y"]) / 2.0}


def _average(values: list[float | None]) -> float:
    valid = [value for value in values if value is not None]
    if not valid:
        return 0.0
    return sum(valid) / len(valid)


def _average_x(first: Mapping[str, float] | None, second: Mapping[str, float] | None) -> float | None:
    if first is None or second is None:
        return None
    return (first["x"] + second["x"]) / 2.0


def _distance(first: Mapping[str, float] | None, second: Mapping[str, float] | None) -> float:
    if first is None or second is None:
        return 0.0
    return hypot(first["x"] - second["x"], first["y"] - second["y"])


def _distance_x(point: Mapping[str, float] | None, center_x: float) -> float:
    if point is None:
        return 0.0
    return abs(point["x"] - center_x)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def label_for_aura(score: int, *, winner: bool, face_detected: bool) -> str:
    if not face_detected:
        return "MYSTERY AURA"
    if winner and score >= 90:
        return "BOOTH FINAL BOSS"
    if winner:
        return "MIRROR VERIFIED"
    if score >= 88:
        return "GLOW RUNNER-UP"
    if score >= 78:
        return "FLASH READY"
    return "WARMUP GLOW"


def crop_upper_body(frame_bgr: Any | None, face: dict[str, Any] | None, zone: str) -> Any | None:
    if frame_bgr is None:
        return None
    height, width = frame_bgr.shape[:2]
    if face is None:
        left = 0 if zone == "p1" else width // 2
        right = width // 2 if zone == "p1" else width
        return frame_bgr[0:height, left:right].copy()

    bbox = face.get("bbox") if isinstance(face.get("bbox"), dict) else {}
    x = float(bbox.get("x", 0.25 if zone == "p1" else 0.75))
    y = float(bbox.get("y", 0.2))
    box_w = float(bbox.get("width", 0.2))
    box_h = float(bbox.get("height", 0.28))
    pad_x = box_w * 0.9
    top_pad = box_h * 0.7
    bottom_pad = box_h * 1.6
    left = int(max(0, (x - pad_x) * width))
    top = int(max(0, (y - top_pad) * height))
    right = int(min(width, (x + box_w + pad_x) * width))
    bottom = int(min(height, (y + box_h + bottom_pad) * height))
    if right <= left or bottom <= top:
        return None
    return frame_bgr[top:bottom, left:right].copy()
