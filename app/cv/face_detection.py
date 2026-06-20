from __future__ import annotations

from typing import Any


class FaceDetectionService:
    def __init__(self, *, min_size_ratio: float = 0.12, cv2_module: Any | None = None) -> None:
        self.min_size_ratio = max(0.02, min(0.5, min_size_ratio))
        self._cv2 = cv2_module
        self._cascade: Any | None = None
        self._load_failed = False

    def detect(self, frame_bgr: Any) -> list[dict[str, Any]]:
        if frame_bgr is None:
            return []
        cv2 = self._load_cv2()
        if cv2 is None:
            return []
        cascade = self._load_cascade(cv2)
        if cascade is None:
            return []

        height, width = frame_bgr.shape[:2]
        if width <= 0 or height <= 0:
            return []

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        min_size = max(24, int(min(width, height) * self.min_size_ratio))
        detections = cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(min_size, min_size),
        )

        faces: list[dict[str, Any]] = []
        for index, detection in enumerate(detections):
            x, y, box_w, box_h = [float(value) for value in detection]
            confidence = min(1.0, max(0.35, (box_w * box_h) / float(width * height) * 8.0))
            faces.append(
                {
                    "face_id": f"face-{index}",
                    "confidence": confidence,
                    "center": {
                        "x": (x + box_w / 2.0) / width,
                        "y": (y + box_h / 2.0) / height,
                    },
                    "bbox": {
                        "x": x / width,
                        "y": y / height,
                        "width": box_w / width,
                        "height": box_h / height,
                    },
                }
            )
        faces.sort(key=lambda face: float(face["confidence"]), reverse=True)
        return faces[:2]

    def _load_cv2(self) -> Any | None:
        if self._cv2 is not None:
            return self._cv2
        try:
            import cv2
        except ImportError:
            self._load_failed = True
            return None
        self._cv2 = cv2
        return cv2

    def _load_cascade(self, cv2: Any) -> Any | None:
        if self._cascade is not None:
            return self._cascade
        if self._load_failed:
            return None
        cascade_path = getattr(getattr(cv2, "data", None), "haarcascades", "") + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(cascade_path)
        if cascade.empty():
            self._load_failed = True
            return None
        self._cascade = cascade
        return cascade
