from __future__ import annotations


def clamp_normalized(value: float) -> float:
    return max(0.0, min(1.0, value))


def encode_bgr_jpeg(frame_bgr: object | None, *, quality: int = 88) -> bytes:
    if frame_bgr is None:
        return b""
    try:
        import cv2
    except Exception:
        return b""
    ok, encoded = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return b""
    return bytes(encoded)
