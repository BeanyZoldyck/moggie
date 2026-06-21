import os
import tempfile
import time

import pygame


def normalized_point(x, y):
    return {"x": max(0.0, min(1.0, float(x))), "y": max(0.0, min(1.0, float(y)))}


class CameraCVBridge:
    def __init__(
        self,
        camera_index=0,
        camera_width=640,
        camera_height=480,
        cv_width=640,
        cv_height=480,
        split_x=0.5,
        cv_fps=15,
    ):
        self.camera_index = camera_index
        self.camera_width = camera_width
        self.camera_height = camera_height
        self.cv_width = cv_width
        self.cv_height = cv_height
        self.split_x = split_x
        self.cv_interval_ms = max(1, int(1000 / cv_fps))

        self.cv2 = None
        self.np = None
        self.capture = None
        self.hand_detector = None
        self.face_mesh = None
        self.face_cascade = None
        self.eye_cascade = None
        self.smile_cascade = None
        self.previous_gray = None
        self.motion_reps = {"player_one": 0, "player_two": 0}
        self.motion_state = {
            "p1": {"active": False, "last_rep_ms": -1_000_000},
            "p2": {"active": False, "last_rep_ms": -1_000_000},
        }
        self.supported_expressions = ("smile", "eyes_closed", "neutral")

        self.display_frame = None
        self.timestamp_ms = None
        self.hands = []
        self.faces = []
        self.detection_frame_id = 0
        self.last_detection_ms = 0
        self.next_retry_at = 0.0
        self.diagnostic = "Camera has not been started."
        self.preview_rect = None
        self.preview_regions = []

    def start(self):
        if self.capture is not None:
            return

        try:
            os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "moggi-matplotlib"))
            import cv2
            import numpy as np
        except ImportError as exc:
            self.diagnostic = f"Camera/CV package missing: {exc.name}"
            self.next_retry_at = time.monotonic() + 3
            return

        self.cv2 = cv2
        self.np = np

        capture = cv2.VideoCapture(self.camera_index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.camera_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.camera_height)

        if not capture.isOpened():
            capture.release()
            self.diagnostic = f"Camera index {self.camera_index} could not be opened."
            self.next_retry_at = time.monotonic() + 3
            return

        self.capture = capture
        self._load_opencv_detectors()
        self._load_optional_mediapipe_solutions()
        self.diagnostic = f"Camera index {self.camera_index} is open."

    def stop(self):
        if self.hand_detector is not None:
            self.hand_detector.close()
            self.hand_detector = None
        if self.face_mesh is not None:
            self.face_mesh.close()
            self.face_mesh = None
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        self.diagnostic = "Camera stopped."

    def reset_motion_counts(self):
        self.motion_reps = {"player_one": 0, "player_two": 0}
        self.motion_state = {
            "p1": {"active": False, "last_rep_ms": -1_000_000},
            "p2": {"active": False, "last_rep_ms": -1_000_000},
        }
        self.previous_gray = None

    def _load_opencv_detectors(self):
        data_dir = getattr(getattr(self.cv2, "data", None), "haarcascades", "")
        self.face_cascade = self.cv2.CascadeClassifier(data_dir + "haarcascade_frontalface_default.xml")
        self.eye_cascade = self.cv2.CascadeClassifier(data_dir + "haarcascade_eye.xml")
        self.smile_cascade = self.cv2.CascadeClassifier(data_dir + "haarcascade_smile.xml")

        if self.face_cascade.empty():
            self.face_cascade = None
        if self.eye_cascade.empty():
            self.eye_cascade = None
        if self.smile_cascade.empty():
            self.smile_cascade = None

    def _load_optional_mediapipe_solutions(self):
        try:
            import mediapipe.solutions.hands as mp_hands
            import mediapipe.solutions.face_mesh as mp_face_mesh
        except ImportError:
            return

        self.hand_detector = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=4,
            min_detection_confidence=0.55,
            min_tracking_confidence=0.55,
        )
        self.face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=2,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.supported_expressions = ("smile", "surprised", "eyes_closed", "wink", "neutral")

    def poll(self):
        if self.capture is None:
            if time.monotonic() >= self.next_retry_at:
                self.start()
            return

        ok, frame = self.capture.read()
        if not ok or frame is None:
            self.diagnostic = "Camera opened but did not return a frame."
            return

        frame = self.cv2.flip(frame, 1)
        self.display_frame = self.cv2.resize(
            frame,
            (self.camera_width, self.camera_height),
            interpolation=self.cv2.INTER_AREA,
        )
        cv_frame = self.cv2.resize(
            self.display_frame,
            (self.cv_width, self.cv_height),
            interpolation=self.cv2.INTER_AREA,
        )
        self.timestamp_ms = pygame.time.get_ticks()
        self.diagnostic = f"Camera index {self.camera_index} streaming."

        if self.timestamp_ms - self.last_detection_ms >= self.cv_interval_ms:
            self.hands = self._detect_hands(cv_frame)
            self.faces = self._detect_faces(cv_frame)
            self.last_detection_ms = self.timestamp_ms
            self.detection_frame_id += 1

    def draw_preview(self, surface, rect, font=None):
        if self.display_frame is None or self.cv2 is None or self.np is None:
            pygame.draw.rect(surface, (18, 10, 34), rect)
            pygame.draw.rect(surface, (50, 255, 120), rect, 2)
            if font:
                rendered = font.render(self.diagnostic, True, (255, 255, 255))
                surface.blit(rendered, rendered.get_rect(center=rect.center))
            self.preview_rect = rect
            self.preview_regions = []
            return rect

        frame_height, frame_width = self.display_frame.shape[:2]
        preview_rect = self._fit_rect(frame_width, frame_height, rect)
        self.preview_rect = preview_rect
        self.preview_regions = [
            {
                "zone": "all",
                "source": (0.0, 0.0, 1.0, 1.0),
                "source_size": (frame_width, frame_height),
                "crop": (0, 0, frame_width, frame_height),
                "dest": preview_rect,
            }
        ]

        pygame.draw.rect(surface, (8, 6, 18), rect)

        frame = self.cv2.resize(
            self.display_frame,
            (preview_rect.width, preview_rect.height),
            interpolation=self.cv2.INTER_AREA,
        )
        rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        rgb = self.np.ascontiguousarray(rgb)
        image = pygame.image.frombuffer(rgb.tobytes(), (preview_rect.width, preview_rect.height), "RGB")
        surface.blit(image, preview_rect)
        pygame.draw.rect(surface, (50, 255, 120), preview_rect, 2)
        return preview_rect

    def draw_zone_preview(self, surface, rect, font=None):
        if self.display_frame is None or self.cv2 is None or self.np is None:
            return self.draw_preview(surface, rect, font)

        pygame.draw.rect(surface, (8, 6, 18), rect)

        frame_height, frame_width = self.display_frame.shape[:2]
        crop = self._blit_crop_fill(surface, self.display_frame, rect)
        self.preview_rect = rect
        self.preview_regions = [
            {
                "zone": "all",
                "source": (0.0, 0.0, 1.0, 1.0),
                "source_size": (frame_width, frame_height),
                "crop": crop,
                "dest": rect,
            }
        ]

        pygame.draw.rect(surface, (50, 255, 120), rect, 2)
        return rect

    def draw_split_preview(self, surface, rect, font=None):
        if self.display_frame is None or self.cv2 is None or self.np is None:
            return self.draw_preview(surface, rect, font)

        pygame.draw.rect(surface, (8, 6, 18), rect)

        gap = 12
        pane_width = (rect.width - gap) // 2
        left_rect = pygame.Rect(rect.left, rect.top, pane_width, rect.height)
        right_rect = pygame.Rect(left_rect.right + gap, rect.top, rect.width - pane_width - gap, rect.height)
        frame_height, frame_width = self.display_frame.shape[:2]
        split_px = int(frame_width * self.split_x)

        panes = [
            ("p1", left_rect, self.display_frame[:, :split_px], (0.0, 0.0, self.split_x, 1.0)),
            ("p2", right_rect, self.display_frame[:, split_px:], (self.split_x, 0.0, 1.0, 1.0)),
        ]

        self.preview_rect = rect
        self.preview_regions = []

        for zone, pane_rect, frame, source in panes:
            crop = self._blit_crop_fill(surface, frame, pane_rect)
            self.preview_regions.append(
                {
                    "zone": zone,
                    "source": source,
                    "source_size": (frame.shape[1], frame.shape[0]),
                    "crop": crop,
                    "dest": pane_rect,
                }
            )
            pygame.draw.rect(surface, (50, 255, 120) if zone == "p1" else (255, 60, 160), pane_rect, 2)

        return rect

    def _fit_rect(self, source_width, source_height, target_rect):
        source_ratio = source_width / source_height
        target_ratio = target_rect.width / target_rect.height

        if source_ratio > target_ratio:
            fitted_width = target_rect.width
            fitted_height = int(fitted_width / source_ratio)
        else:
            fitted_height = target_rect.height
            fitted_width = int(fitted_height * source_ratio)

        fitted = pygame.Rect(0, 0, fitted_width, fitted_height)
        fitted.center = target_rect.center
        return fitted

    def _blit_crop_fill(self, surface, frame, dest_rect):
        source_height, source_width = frame.shape[:2]
        source_ratio = source_width / source_height
        target_ratio = dest_rect.width / dest_rect.height

        if source_ratio > target_ratio:
            crop_height = source_height
            crop_width = int(crop_height * target_ratio)
            crop_x = max(0, (source_width - crop_width) // 2)
            crop_y = 0
        else:
            crop_width = source_width
            crop_height = int(crop_width / target_ratio)
            crop_x = 0
            crop_y = max(0, (source_height - crop_height) // 2)

        cropped = frame[crop_y:crop_y + crop_height, crop_x:crop_x + crop_width]
        resized = self.cv2.resize(cropped, (dest_rect.width, dest_rect.height), interpolation=self.cv2.INTER_AREA)
        rgb = self.cv2.cvtColor(resized, self.cv2.COLOR_BGR2RGB)
        rgb = self.np.ascontiguousarray(rgb)
        image = pygame.image.frombuffer(rgb.tobytes(), (dest_rect.width, dest_rect.height), "RGB")
        surface.blit(image, dest_rect)
        return crop_x, crop_y, crop_width, crop_height

    def draw_hand_overlay(self, surface, rect=None):
        for hand in self.hands:
            points = hand.get("landmarks", [])
            color = (50, 255, 120) if hand.get("zone") == "p1" else (0, 180, 255)
            for point in points:
                position = self._point_to_screen(point, rect, hand.get("zone"))
                if position:
                    pygame.draw.circle(surface, color, position, 4)
            palm = hand.get("palm_center")
            if palm:
                position = self._point_to_screen(palm, rect, hand.get("zone"))
                if position:
                    pygame.draw.circle(surface, color, position, 10, 2)

    def draw_face_overlay(self, surface, rect=None):
        for face in self.faces:
            bbox = face.get("bbox", {})
            color = (50, 255, 120) if face.get("zone") == "p1" else (255, 60, 160)
            top_left = self._point_to_screen(
                {"x": bbox.get("x", 0), "y": bbox.get("y", 0)},
                rect,
                face.get("zone"),
            )
            bottom_right = self._point_to_screen(
                {
                    "x": float(bbox.get("x", 0)) + float(bbox.get("width", 0)),
                    "y": float(bbox.get("y", 0)) + float(bbox.get("height", 0)),
                },
                rect,
                face.get("zone"),
            )

            if top_left and bottom_right:
                left = min(top_left[0], bottom_right[0])
                top = min(top_left[1], bottom_right[1])
                right = max(top_left[0], bottom_right[0])
                bottom = max(top_left[1], bottom_right[1])
                box = pygame.Rect(left, top, max(1, right - left), max(1, bottom - top))
                region = self._region_for_zone(face.get("zone"))
                if region:
                    box = box.clip(region["dest"])
                if box.width > 0 and box.height > 0:
                    pygame.draw.rect(surface, color, box, 3)

    def _point_to_screen(self, point, fallback_rect=None, preferred_zone=None):
        region = self._region_for_zone(preferred_zone)

        if region is None:
            point_x = float(point["x"])
            for candidate in self.preview_regions:
                source_left, _source_top, source_right, _source_bottom = candidate["source"]
                if source_left <= point_x <= source_right:
                    region = candidate
                    break

        if region is None:
            rect = fallback_rect or self.preview_rect
            if rect is None:
                return None
            return (
                rect.left + int(float(point["x"]) * rect.width),
                rect.top + int(float(point["y"]) * rect.height),
            )

        source_left, source_top, source_right, source_bottom = region["source"]
        source_width, source_height = region["source_size"]
        crop_x, crop_y, crop_width, crop_height = region["crop"]
        dest = region["dest"]

        local_x = (float(point["x"]) - source_left) / max(0.0001, source_right - source_left)
        local_y = (float(point["y"]) - source_top) / max(0.0001, source_bottom - source_top)
        source_px_x = local_x * source_width
        source_px_y = local_y * source_height
        screen_x = dest.left + int((source_px_x - crop_x) * dest.width / max(1, crop_width))
        screen_y = dest.top + int((source_px_y - crop_y) * dest.height / max(1, crop_height))
        return screen_x, screen_y

    def _region_for_zone(self, zone):
        if zone is None:
            return None

        for region in self.preview_regions:
            if region["zone"] == zone:
                return region

        for region in self.preview_regions:
            if region["zone"] == "all":
                return region

        return None

    def face_for_zone(self, zone):
        zone_faces = [face for face in self.faces if face.get("zone") == zone]
        if not zone_faces:
            return None
        return max(zone_faces, key=lambda face: float(face.get("confidence", 0.0)))

    def _detect_hands(self, frame_bgr):
        if self.hand_detector is None:
            return self._detect_motion_hands(frame_bgr)

        rgb = self.cv2.cvtColor(frame_bgr, self.cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = self.hand_detector.process(rgb)
        landmarks = result.multi_hand_landmarks or []
        handedness = result.multi_handedness or []
        hands = []

        for index, hand_landmarks in enumerate(landmarks):
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

            zone = self._zone_for_x(palm_center["x"])
            hands.append(
                {
                    "hand_id": f"hand-{index}",
                    "confidence": confidence,
                    "handedness": label,
                    "zone": zone,
                    "palm_center": palm_center,
                    "landmarks": points,
                }
            )

        return hands

    def _detect_motion_hands(self, frame_bgr):
        gray = self.cv2.cvtColor(frame_bgr, self.cv2.COLOR_BGR2GRAY)
        gray = self.cv2.GaussianBlur(gray, (21, 21), 0)

        if self.previous_gray is None:
            self.previous_gray = gray
            return []

        diff = self.cv2.absdiff(self.previous_gray, gray)
        self.previous_gray = gray
        thresh = self.cv2.threshold(diff, 28, 255, self.cv2.THRESH_BINARY)[1]
        thresh = self.cv2.dilate(thresh, None, iterations=2)

        height, width = thresh.shape[:2]
        now_ms = pygame.time.get_ticks()
        hands = []

        zones = {
            "p1": (0, int(width * self.split_x), "player_one", 0.25),
            "p2": (int(width * self.split_x), width, "player_two", 0.75),
        }

        for zone, (left, right, player, center_x) in zones.items():
            zone_mask = thresh[:, left:right]
            movement = self.cv2.countNonZero(zone_mask) / float(max(1, zone_mask.size))
            state = self.motion_state[zone]

            if movement > 0.045 and not state["active"] and now_ms - state["last_rep_ms"] >= 500:
                self.motion_reps[player] += 1
                state["active"] = True
                state["last_rep_ms"] = now_ms
            elif movement < 0.018:
                state["active"] = False

            if movement > 0.018:
                center_y = 0.48 if state["active"] else 0.58
                spread = min(0.18, 0.05 + movement * 1.4)
                hands.extend(
                    [
                        {
                            "hand_id": f"{zone}-motion-a",
                            "confidence": 0.75,
                            "source": "motion",
                            "zone": zone,
                            "palm_center": normalized_point(center_x - spread, center_y),
                            "landmarks": [normalized_point(center_x - spread, center_y)],
                        },
                        {
                            "hand_id": f"{zone}-motion-b",
                            "confidence": 0.75,
                            "source": "motion",
                            "zone": zone,
                            "palm_center": normalized_point(center_x + spread, center_y),
                            "landmarks": [normalized_point(center_x + spread, center_y)],
                        },
                    ]
                )

        return hands

    def _detect_faces(self, frame_bgr):
        if self.face_mesh is None:
            return self._detect_opencv_faces(frame_bgr)

        rgb = self.cv2.cvtColor(frame_bgr, self.cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = self.face_mesh.process(rgb)
        face_landmarks = result.multi_face_landmarks or []
        faces = []

        for index, landmarks in enumerate(face_landmarks):
            points = [normalized_point(point.x, point.y) for point in landmarks.landmark]
            xs = [point["x"] for point in points]
            ys = [point["y"] for point in points]
            left = min(xs)
            top = min(ys)
            right = max(xs)
            bottom = max(ys)
            center = normalized_point((left + right) / 2, (top + bottom) / 2)
            zone = self._zone_for_x(center["x"])

            faces.append(
                {
                    "face_id": f"face-{index}",
                    "confidence": 1.0,
                    "zone": zone,
                    "center": center,
                    "bbox": {
                        "x": left,
                        "y": top,
                        "width": right - left,
                        "height": bottom - top,
                    },
                    "landmarks": points,
                    "expression_features": self._expression_features(points),
                }
            )

        return faces

    def _detect_opencv_faces(self, frame_bgr):
        if self.face_cascade is None:
            return []

        height, width = frame_bgr.shape[:2]
        gray = self.cv2.cvtColor(frame_bgr, self.cv2.COLOR_BGR2GRAY)
        min_size = max(36, int(min(width, height) * 0.12))
        detections = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(min_size, min_size),
        )
        faces = []

        for index, detection in enumerate(detections[:2]):
            x, y, box_w, box_h = [int(value) for value in detection]
            face_gray = gray[y:y + box_h, x:x + box_w]
            center = normalized_point((x + box_w / 2) / width, (y + box_h / 2) / height)
            zone = self._zone_for_x(center["x"])
            confidence = min(1.0, max(0.35, (box_w * box_h) / float(width * height) * 8.0))

            faces.append(
                {
                    "face_id": f"face-{index}",
                    "confidence": confidence,
                    "zone": zone,
                    "center": center,
                    "bbox": {
                        "x": x / width,
                        "y": y / height,
                        "width": box_w / width,
                        "height": box_h / height,
                    },
                    "landmarks": [],
                    "expression_features": self._opencv_expression_features(face_gray),
                }
            )

        faces.sort(key=lambda face: float(face.get("confidence", 0.0)), reverse=True)
        return faces

    def _opencv_expression_features(self, face_gray):
        smiles = []
        eyes = []

        if self.smile_cascade is not None and face_gray.size:
            smiles = self.smile_cascade.detectMultiScale(
                face_gray,
                scaleFactor=1.7,
                minNeighbors=20,
                minSize=(18, 18),
            )

        if self.eye_cascade is not None and face_gray.size:
            upper_face = face_gray[: max(1, face_gray.shape[0] // 2), :]
            eyes = self.eye_cascade.detectMultiScale(
                upper_face,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(12, 12),
            )

        smile = 0.85 if len(smiles) > 0 else 0.0
        eyes_closed = 0.8 if len(eyes) == 0 else 0.0
        active = max(smile, eyes_closed)

        return {
            "smile": smile,
            "mouth_open": 0.0,
            "left_eye_closed": eyes_closed,
            "right_eye_closed": eyes_closed,
            "eyes_closed": eyes_closed,
            "wink": 0.0,
            "neutral": max(0.0, 1.0 - active),
        }

    def _expression_features(self, points):
        mouth_width = self._distance(points, 61, 291)
        mouth_open = self._distance(points, 13, 14)
        left_eye_open = self._distance(points, 159, 145)
        right_eye_open = self._distance(points, 386, 374)

        smile_ratio = self._ratio(mouth_width, mouth_open, default=0.0)
        smile = self._clamp((smile_ratio - 4.2) / 2.0)
        mouth_open_score = self._clamp(self._ratio(mouth_open, mouth_width, default=0.0) * 5.0)
        left_closed = self._clamp(1.0 - self._ratio(left_eye_open, mouth_width, default=0.05) * 18.0)
        right_closed = self._clamp(1.0 - self._ratio(right_eye_open, mouth_width, default=0.05) * 18.0)
        eyes_closed = min(left_closed, right_closed)
        wink = abs(left_closed - right_closed)
        active = max(smile, mouth_open_score, eyes_closed, wink)

        return {
            "smile": smile,
            "mouth_open": mouth_open_score,
            "left_eye_closed": left_closed,
            "right_eye_closed": right_closed,
            "eyes_closed": eyes_closed,
            "wink": wink,
            "neutral": 1.0 - active,
        }

    def _zone_for_x(self, x):
        return "p1" if float(x) < self.split_x else "p2"

    def _distance(self, points, left_index, right_index):
        if left_index >= len(points) or right_index >= len(points):
            return 0.0
        left = points[left_index]
        right = points[right_index]
        return ((left["x"] - right["x"]) ** 2 + (left["y"] - right["y"]) ** 2) ** 0.5

    def _ratio(self, numerator, denominator, *, default):
        if denominator <= 0.0001:
            return default
        return numerator / denominator

    def _clamp(self, value):
        return max(0.0, min(1.0, value))
