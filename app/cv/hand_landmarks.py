from __future__ import annotations

from typing import Any

from app.core.app_event import normalized_point
from app.cv.zone_assignment import assign_hand_detections


class HandLandmarkService:
    def __init__(
        self,
        *,
        max_hands: int = 4,
        min_confidence: float = 0.55,
        split_x: float = 0.5,
        mediapipe_module: Any | None = None,
        cv2_module: Any | None = None,
    ) -> None:
        self.max_hands = max(1, min(4, max_hands))
        self.min_confidence = max(0.0, min(1.0, min_confidence))
        self.split_x = max(0.0, min(1.0, split_x))
        self._mp = mediapipe_module
        self._cv2 = cv2_module
        self._hands: Any | None = None
        self.available = False
        self.diagnostic = "Hand landmark detector has not been started."

    def start(self) -> None:
        if self._hands is not None:
            return
        if self._mp is None:
            try:
                import mediapipe as mp
            except ImportError:
                self.diagnostic = "MediaPipe is not installed; hand landmarks are unavailable."
                return
            self._mp = mp
        if self._cv2 is None:
            try:
                import cv2
            except ImportError:
                self.diagnostic = "OpenCV is not installed; hand landmarks are unavailable."
                return
            self._cv2 = cv2

        self._hands = self._mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=self.max_hands,
            min_detection_confidence=self.min_confidence,
            min_tracking_confidence=self.min_confidence,
        )
        self.available = True
        self.diagnostic = f"Hand landmark detector tracking up to {self.max_hands} hands."

    def stop(self) -> None:
        if self._hands is not None:
            self._hands.close()
            self._hands = None
        self.available = False

    def detect(self, frame_bgr: Any) -> list[dict[str, Any]]:
        if self._hands is None:
            self.start()
        if self._hands is None or self._cv2 is None:
            return []

        rgb = self._cv2.cvtColor(frame_bgr, self._cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = self._hands.process(rgb)
        landmarks = result.multi_hand_landmarks or []
        handedness = result.multi_handedness or []
        raw_hands: list[dict[str, Any]] = []

        for index, hand_landmarks in enumerate(landmarks[: self.max_hands]):
            points = [normalized_point(point.x, point.y) for point in hand_landmarks.landmark]
            palm_indices = [0, 5, 9, 13, 17]
            palm_center = normalized_point(
                sum(points[i]["x"] for i in palm_indices) / len(palm_indices),
                sum(points[i]["y"] for i in palm_indices) / len(palm_indices),
            )
            confidence = 1.0
            label = None
            if index < len(handedness):
                classification = handedness[index].classification[0]
                confidence = float(classification.score)
                label = classification.label
            raw_hands.append(
                {
                    "hand_id": f"hand-{index}",
                    "confidence": confidence,
                    "handedness": label,
                    "palm_center": palm_center,
                    "landmarks": points,
                }
            )

        return assign_hand_detections(raw_hands, split_x=self.split_x)
