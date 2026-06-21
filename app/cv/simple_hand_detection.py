from __future__ import annotations

from typing import Any

from app.core.app_event import normalized_point
from app.cv.zone_assignment import assign_hand_detections


class SimpleHandDetectionService:
    """Lightweight OpenCV fallback when MediaPipe is unavailable.

    This is not a landmark model. It extracts the largest skin-colored contours
    and emits hand-like detections with palm centers and coarse landmark points,
    which is enough for zone assignment, overlay, and 67 Challenge distance
    counting on the QNX hackathon image.
    """

    def __init__(
        self,
        *,
        max_hands: int = 4,
        min_area_ratio: float = 0.004,
        max_area_ratio: float = 0.12,
        split_x: float = 0.5,
        cv2_module: Any | None = None,
        numpy_module: Any | None = None,
        hand_region_top: float = 0.36,
    ) -> None:
        self.max_hands = max(1, min(8, max_hands))
        self.min_area_ratio = max(0.0005, min(0.05, min_area_ratio))
        self.max_area_ratio = max(self.min_area_ratio, min(0.4, max_area_ratio))
        self.split_x = max(0.0, min(1.0, split_x))
        self.hand_region_top = max(0.0, min(0.75, hand_region_top))
        self._cv2 = cv2_module
        self._np = numpy_module
        self._previous_gray: Any | None = None
        self.available = False
        self.diagnostic = "Simple hand detector has not been started."

    def start(self) -> None:
        if self._cv2 is None:
            try:
                import cv2
            except ImportError:
                self.diagnostic = "OpenCV is not installed; fallback hand detection is unavailable."
                return
            self._cv2 = cv2
        if self._np is None:
            try:
                import numpy as np
            except ImportError:
                self.diagnostic = "NumPy is not installed; fallback hand detection is unavailable."
                return
            self._np = np
        self.available = True
        self.diagnostic = f"Simple hand detector tracking up to {self.max_hands} contours."

    def stop(self) -> None:
        self.available = False
        self._previous_gray = None

    def detect(self, frame_bgr: Any) -> list[dict[str, Any]]:
        if not self.available:
            self.start()
        if not self.available or self._cv2 is None or self._np is None:
            return []

        cv2 = self._cv2
        np = self._np
        height, width = frame_bgr.shape[:2]
        if width <= 0 or height <= 0:
            return []

        ycrcb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YCrCb)
        skin = cv2.inRange(
            ycrcb,
            np.array([0, 133, 77], dtype=np.uint8),
            np.array([255, 180, 135], dtype=np.uint8),
        )
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(skin, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        motion = self._motion_mask(frame_bgr)
        if motion is not None:
            mask = cv2.bitwise_or(mask, motion)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        frame_area = width * height
        min_area = frame_area * self.min_area_ratio
        max_area = frame_area * self.max_area_ratio
        candidates: list[tuple[str, float, float, float, Any, int, int, int, int]] = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < min_area or area > max_area:
                continue
            x, y, box_w, box_h = cv2.boundingRect(contour)
            if box_w <= 0 or box_h <= 0:
                continue
            if box_w > width * 0.42 or box_h > height * 0.55:
                continue
            aspect = box_w / float(box_h)
            if aspect < 0.25 or aspect > 4.0:
                continue
            center_y_norm = (y + box_h / 2.0) / height
            motion_density = self._motion_density(motion, x, y, box_w, box_h)
            if center_y_norm < self.hand_region_top and motion_density < 0.32:
                continue
            if self._looks_like_static_face(
                center_y_norm=center_y_norm,
                aspect=aspect,
                box_w=box_w,
                box_h=box_h,
                frame_w=width,
                frame_h=height,
                motion_density=motion_density,
            ):
                continue
            score = self._candidate_score(area, center_y_norm=center_y_norm, motion_density=motion_density)
            zone = "p1" if (x + box_w / 2.0) / width < self.split_x else "p2"
            candidates.append((zone, score, area, motion_density, contour, x, y, box_w, box_h))

        raw_hands: list[dict[str, Any]] = []
        for _, _, area, motion_density, contour, x, y, box_w, box_h in self._select_balanced_candidates(candidates):
            moments = cv2.moments(contour)
            if moments["m00"]:
                center_x = float(moments["m10"] / moments["m00"])
                center_y = float(moments["m01"] / moments["m00"])
            else:
                center_x = x + box_w / 2.0
                center_y = y + box_h / 2.0

            palm = normalized_point(center_x / width, center_y / height)
            landmarks = [
                palm,
                normalized_point((x + box_w / 2.0) / width, y / height),
                normalized_point((x + box_w) / width, (y + box_h * 0.35) / height),
                normalized_point((x + box_w * 0.75) / width, (y + box_h) / height),
                normalized_point(x / width, (y + box_h * 0.35) / height),
            ]
            confidence = min(1.0, max(0.50, area / float(width * height) * 8.0 + motion_density * 0.35))
            raw_hands.append(
                {
                    "hand_id": f"simple-hand-{len(raw_hands)}",
                    "confidence": confidence,
                    "palm_center": palm,
                    "landmarks": landmarks,
                    "bbox": {
                        "x": x / width,
                        "y": y / height,
                        "width": box_w / width,
                        "height": box_h / height,
                    },
                    "motion_score": motion_density,
                    "source": "simple_contour",
                }
            )

        return assign_hand_detections(raw_hands, split_x=self.split_x)

    def _motion_mask(self, frame_bgr: Any) -> Any | None:
        cv2 = self._cv2
        np = self._np
        if cv2 is None or np is None:
            return None
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 0)
        previous = self._previous_gray
        self._previous_gray = gray
        if previous is None:
            return None
        diff = cv2.absdiff(previous, gray)
        _, motion = cv2.threshold(diff, 14, 255, cv2.THRESH_BINARY)
        kernel = np.ones((3, 3), np.uint8)
        return cv2.dilate(motion, kernel, iterations=2)

    def _motion_density(self, motion: Any | None, x: int, y: int, box_w: int, box_h: int) -> float:
        np = self._np
        if motion is None or np is None or box_w <= 0 or box_h <= 0:
            return 0.0
        roi = motion[y : y + box_h, x : x + box_w]
        if roi.size == 0:
            return 0.0
        return min(1.0, float(np.count_nonzero(roi)) / float(roi.size))

    def _looks_like_static_face(
        self,
        *,
        center_y_norm: float,
        aspect: float,
        box_w: int,
        box_h: int,
        frame_w: int,
        frame_h: int,
        motion_density: float,
    ) -> bool:
        width_ratio = box_w / float(frame_w)
        height_ratio = box_h / float(frame_h)
        upper_frame = center_y_norm < 0.58
        face_shape = 0.55 <= aspect <= 1.35 and 0.08 <= width_ratio <= 0.30 and 0.12 <= height_ratio <= 0.50
        return upper_frame and face_shape and motion_density < 0.30

    def _candidate_score(self, area: float, *, center_y_norm: float, motion_density: float) -> float:
        motion_boost = 0.45 + motion_density * 5.2
        if center_y_norm < self.hand_region_top:
            vertical_weight = 0.20 + motion_density * 0.65
        elif center_y_norm < 0.52:
            vertical_weight = 0.65 + motion_density * 0.50
        else:
            vertical_weight = 1.15
        return area * motion_boost * vertical_weight

    def _select_balanced_candidates(
        self,
        candidates: list[tuple[str, float, float, float, Any, int, int, int, int]],
    ) -> list[tuple[str, float, float, float, Any, int, int, int, int]]:
        per_zone_limit = 2 if self.max_hands >= 4 else 1
        selected: list[tuple[str, float, float, float, Any, int, int, int, int]] = []
        used_ids: set[int] = set()

        for zone in ("p1", "p2"):
            zone_candidates = sorted(
                [candidate for candidate in candidates if candidate[0] == zone],
                key=lambda candidate: candidate[1],
                reverse=True,
            )
            for candidate in zone_candidates[:per_zone_limit]:
                selected.append(candidate)
                used_ids.add(id(candidate[4]))

        if len(selected) < self.max_hands:
            for candidate in sorted(candidates, key=lambda candidate: candidate[1], reverse=True):
                if id(candidate[4]) in used_ids:
                    continue
                selected.append(candidate)
                if len(selected) >= self.max_hands:
                    break

        return sorted(selected[: self.max_hands], key=lambda candidate: candidate[1], reverse=True)
