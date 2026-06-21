from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.app_event import normalized_point
from app.cv.mediapipe_compat import import_mediapipe


FACE_MESH_LANDMARKS = {
    "nose_tip": 1,
    "chin": 152,
    "left_cheek": 234,
    "right_cheek": 454,
    "mouth_left": 61,
    "mouth_right": 291,
    "upper_lip": 13,
    "lower_lip": 14,
    "left_eye_outer": 33,
    "left_eye_inner": 133,
    "left_eye_top": 159,
    "left_eye_bottom": 145,
    "right_eye_inner": 362,
    "right_eye_outer": 263,
    "right_eye_top": 386,
    "right_eye_bottom": 374,
}


class FaceDetectionService:
    def __init__(
        self,
        *,
        min_size_ratio: float = 0.12,
        backend: str = "mediapipe",
        cv2_module: Any | None = None,
        mediapipe_module: Any | None = None,
    ) -> None:
        self.min_size_ratio = max(0.02, min(0.5, min_size_ratio))
        self.backend = backend if backend in {"mediapipe", "cascade"} else "mediapipe"
        self._cv2 = cv2_module
        self._mp = mediapipe_module
        self._face_mesh: Any | None = None
        self._cascade: Any | None = None
        self._load_failed = False
        self._mesh_load_failed = False

    def detect(self, frame_bgr: Any) -> list[dict[str, Any]]:
        if frame_bgr is None:
            return []
        cv2 = self._load_cv2()
        if cv2 is None:
            return []

        if self.backend == "mediapipe":
            mesh_faces = self._detect_with_face_mesh(frame_bgr, cv2)
            if mesh_faces:
                return mesh_faces

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

    def stop(self) -> None:
        if self._face_mesh is not None:
            self._face_mesh.close()
            self._face_mesh = None

    def _detect_with_face_mesh(self, frame_bgr: Any, cv2: Any) -> list[dict[str, Any]]:
        face_mesh = self._load_face_mesh()
        if face_mesh is None:
            return []

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = face_mesh.process(rgb)
        landmarks = result.multi_face_landmarks or []
        return [_face_from_landmarks(index, face.landmark, frame_bgr=frame_bgr, cv2=cv2) for index, face in enumerate(landmarks[:2])]

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

    def _load_face_mesh(self) -> Any | None:
        if self._face_mesh is not None:
            return self._face_mesh
        if self._mesh_load_failed:
            return None
        if self._mp is None:
            try:
                mp = import_mediapipe()
            except ImportError:
                self._mesh_load_failed = True
                return None
            self._mp = mp

        try:
            self._face_mesh = self._mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=2,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        except (AttributeError, TypeError, ValueError):
            self._mesh_load_failed = True
            return None
        return self._face_mesh

    def _load_cascade(self, cv2: Any) -> Any | None:
        if self._cascade is not None:
            return self._cascade
        if self._load_failed:
            return None
        cascade_path = getattr(getattr(cv2, "data", None), "haarcascades", "") + "haarcascade_frontalface_default.xml"
        if not cascade_path or not Path(cascade_path).exists():
            self._load_failed = True
            return None
        cascade = cv2.CascadeClassifier(cascade_path)
        if cascade.empty():
            self._load_failed = True
            return None
        self._cascade = cascade
        return cascade


def _face_from_landmarks(
    index: int,
    landmarks: list[Any],
    *,
    frame_bgr: Any | None = None,
    cv2: Any | None = None,
) -> dict[str, Any]:
    points = [normalized_point(float(point.x), float(point.y)) for point in landmarks]
    xs = [point["x"] for point in points]
    ys = [point["y"] for point in points]
    bbox = {
        "x": min(xs),
        "y": min(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }
    named_landmarks = {
        name: points[landmark_index]
        for name, landmark_index in FACE_MESH_LANDMARKS.items()
        if landmark_index < len(points)
    }
    face = {
        "face_id": f"face-{index}",
        "confidence": 1.0,
        "center": normalized_point(bbox["x"] + bbox["width"] / 2.0, bbox["y"] + bbox["height"] / 2.0),
        "bbox": bbox,
        "landmarks": named_landmarks,
    }
    tongue_out = _tongue_out_score(frame_bgr, cv2, named_landmarks)
    if tongue_out > 0.0:
        face["expression_features"] = {"tongue_out": tongue_out}
    return face


def _tongue_out_score(frame_bgr: Any | None, cv2: Any | None, landmarks: dict[str, dict[str, float]]) -> float:
    if frame_bgr is None or cv2 is None:
        return 0.0
    mouth_left = landmarks.get("mouth_left")
    mouth_right = landmarks.get("mouth_right")
    upper_lip = landmarks.get("upper_lip")
    lower_lip = landmarks.get("lower_lip")
    if mouth_left is None or mouth_right is None or upper_lip is None or lower_lip is None:
        return 0.0

    frame_h, frame_w = frame_bgr.shape[:2]
    mouth_w = abs(mouth_right["x"] - mouth_left["x"])
    if mouth_w <= 0.01:
        return 0.0
    mouth_open = abs(lower_lip["y"] - upper_lip["y"])
    if mouth_open / mouth_w < 0.11:
        return 0.0
    x1 = int(max(0, (min(mouth_left["x"], mouth_right["x"]) - mouth_w * 0.18) * frame_w))
    x2 = int(min(frame_w, (max(mouth_left["x"], mouth_right["x"]) + mouth_w * 0.18) * frame_w))
    y1 = int(max(0, (lower_lip["y"] - mouth_w * 0.02) * frame_h))
    y2 = int(min(frame_h, (lower_lip["y"] + mouth_w * 0.58) * frame_h))
    if x2 <= x1 or y2 <= y1:
        return 0.0

    roi = frame_bgr[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    red_low = cv2.inRange(hsv, (0, 45, 55), (16, 255, 255))
    red_high = cv2.inRange(hsv, (160, 45, 55), (179, 255, 255))
    pink = cv2.inRange(hsv, (135, 35, 60), (179, 255, 255))
    warm = cv2.inRange(hsv, (0, 30, 65), (24, 210, 255))
    color_ratio = float(cv2.countNonZero(red_low | red_high | pink | warm)) / float(roi.shape[0] * roi.shape[1])
    return max(0.0, min(1.0, (color_ratio - 0.055) / 0.16))
