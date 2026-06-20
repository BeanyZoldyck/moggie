from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


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


def score_aura(
    *,
    session_id: str,
    display_name: str,
    zone: str,
    face: dict[str, Any] | None,
    manual_override: bool = False,
) -> int:
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
