from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from app.config import MoggieConfig
from app.core.app_event import (
    EVENT_CV_FACE_LANDMARKS,
    EVENT_CV_HAND_LANDMARKS,
    AppEvent,
    face_landmarks_payload,
    hand_landmarks_payload,
    normalized_point,
)
from app.core.event_bus import EventBus
from app.core.worker import ManagedWorker
from app.cv.face_detection import FaceDetectionService
from app.cv.hand_landmarks import HandLandmarkService
from app.cv.zone_assignment import (
    assign_face,
    assign_face_detections,
    assign_hand,
    assign_hand_detections,
    summarize_zone_assignments,
)
from app.services.camera_service import CameraService


@dataclass(frozen=True)
class LatestCVState:
    timestamp_ms: int | None = None
    hand_landmarks: dict[str, Any] = field(default_factory=dict)
    face_landmarks: dict[str, Any] = field(default_factory=dict)


class CVService:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        camera_service: CameraService | None = None,
        cv_fps: int = 15,
        zone_split_x: float = 0.5,
        max_hands: int = 4,
        min_hand_confidence: float = 0.55,
        mock_events: bool = False,
    ) -> None:
        self.event_bus = event_bus
        self.camera_service = camera_service
        self.cv_fps = max(1, cv_fps)
        self.zone_split_x = max(0.0, min(1.0, zone_split_x))
        self.hand_landmarks = HandLandmarkService(
            max_hands=max_hands,
            min_confidence=min_hand_confidence,
            split_x=self.zone_split_x,
        )
        self.face_detection = FaceDetectionService()
        self.mock_events = mock_events
        self._lock = Lock()
        self._latest_state = LatestCVState()
        self._worker = _CVWorker(self)

    @classmethod
    def from_config(
        cls,
        config: MoggieConfig,
        *,
        event_bus: EventBus,
        camera_service: CameraService | None = None,
        mock_events: bool = False,
    ) -> "CVService":
        return cls(
            event_bus=event_bus,
            camera_service=camera_service,
            cv_fps=config.cv_fps,
            zone_split_x=config.zone_split_x,
            max_hands=config.sixty_seven_max_hands,
            min_hand_confidence=config.sixty_seven_min_confidence,
            mock_events=mock_events,
        )

    @property
    def is_running(self) -> bool:
        return self._worker.is_running

    def start(self) -> None:
        self._worker.start()

    def stop(self) -> None:
        self._worker.stop()
        self.hand_landmarks.stop()

    def latest_state(self) -> LatestCVState:
        with self._lock:
            return LatestCVState(
                timestamp_ms=self._latest_state.timestamp_ms,
                hand_landmarks=dict(self._latest_state.hand_landmarks),
                face_landmarks=dict(self._latest_state.face_landmarks),
            )

    def record_event(self, event: AppEvent) -> None:
        if event.type == EVENT_CV_HAND_LANDMARKS:
            with self._lock:
                self._latest_state = LatestCVState(
                    timestamp_ms=event.timestamp_ms,
                    hand_landmarks=dict(event.payload),
                    face_landmarks=self._latest_state.face_landmarks,
                )
        elif event.type == EVENT_CV_FACE_LANDMARKS:
            with self._lock:
                self._latest_state = LatestCVState(
                    timestamp_ms=event.timestamp_ms,
                    hand_landmarks=self._latest_state.hand_landmarks,
                    face_landmarks=dict(event.payload),
                )

    def publish(self, event: AppEvent) -> None:
        self.record_event(event)
        self.event_bus.publish(event)

    def _build_mock_events(self, frame_number: int) -> list[AppEvent]:
        phase = (frame_number % self.cv_fps) / self.cv_fps
        left_x = 0.25 + 0.04 * phase
        right_x = 0.75 - 0.04 * phase
        raw_hands = [
            {
                "hand_id": "mock-left",
                "confidence": 0.92,
                "palm_center": normalized_point(left_x, 0.58),
                "landmarks": [normalized_point(left_x, 0.58), normalized_point(left_x, 0.48)],
            },
            {
                "hand_id": "mock-right",
                "confidence": 0.91,
                "palm_center": normalized_point(right_x, 0.58),
                "landmarks": [normalized_point(right_x, 0.58), normalized_point(right_x, 0.48)],
            },
        ]
        raw_faces = [
            {
                "face_id": "mock-p1",
                "confidence": 0.88,
                "center": normalized_point(0.25, 0.38),
                "bbox": {"x": 0.18, "y": 0.18, "width": 0.14, "height": 0.26},
                "landmarks": [normalized_point(0.25, 0.34), normalized_point(0.22, 0.38)],
            },
            {
                "face_id": "mock-p2",
                "confidence": 0.87,
                "center": normalized_point(0.75, 0.38),
                "bbox": {"x": 0.68, "y": 0.18, "width": 0.14, "height": 0.26},
                "landmarks": [normalized_point(0.75, 0.34), normalized_point(0.78, 0.38)],
            },
        ]
        hand_assignments = [assign_hand(hand, split_x=self.zone_split_x) for hand in raw_hands]
        face_assignments = [assign_face(face, split_x=self.zone_split_x) for face in raw_faces]
        hands = assign_hand_detections(raw_hands, split_x=self.zone_split_x)
        faces = assign_face_detections(raw_faces, split_x=self.zone_split_x)
        frame_id = f"mock-{frame_number}"
        return [
            AppEvent.create(
                EVENT_CV_HAND_LANDMARKS,
                payload=hand_landmarks_payload(
                    hands,
                    frame_id=frame_id,
                    zone_assignment=summarize_zone_assignments(hand_assignments),
                ),
            ),
            AppEvent.create(
                EVENT_CV_FACE_LANDMARKS,
                payload=face_landmarks_payload(
                    faces,
                    frame_id=frame_id,
                    zone_assignment=summarize_zone_assignments(face_assignments),
                ),
            ),
        ]

    def _build_camera_events(self) -> list[AppEvent]:
        if self.camera_service is None:
            return []
        frame = self.camera_service.latest_cv_frame()
        if frame is None:
            return []

        hands = self.hand_landmarks.detect(frame)
        hand_assignments = []
        for hand in hands:
            try:
                hand_assignments.append(assign_hand(hand, split_x=self.zone_split_x))
            except (TypeError, ValueError, KeyError):
                continue
        faces = self.face_detection.detect(frame)
        face_assignments = []
        for face in faces:
            try:
                face_assignments.append(assign_face(face, split_x=self.zone_split_x))
            except (TypeError, ValueError, KeyError):
                continue
        return [
            AppEvent.create(
                EVENT_CV_HAND_LANDMARKS,
                payload=hand_landmarks_payload(
                    hands,
                    frame_id=f"camera-{id(frame)}",
                    zone_assignment=summarize_zone_assignments(hand_assignments),
                ),
            ),
            AppEvent.create(
                EVENT_CV_FACE_LANDMARKS,
                payload=face_landmarks_payload(
                    assign_face_detections(faces, split_x=self.zone_split_x),
                    frame_id=f"camera-{id(frame)}",
                    zone_assignment=summarize_zone_assignments(face_assignments),
                ),
            )
        ]


class _CVWorker(ManagedWorker):
    def __init__(self, service: CVService) -> None:
        super().__init__(name="moggie-cv-worker")
        self.service = service

    def run(self) -> None:
        frame_number = 0
        interval_seconds = 1.0 / self.service.cv_fps
        while not self.should_stop:
            if self.service.mock_events:
                for event in self.service._build_mock_events(frame_number):
                    self.service.publish(event)
            else:
                for event in self.service._build_camera_events():
                    self.service.publish(event)
            frame_number += 1
            self.wait(interval_seconds)
