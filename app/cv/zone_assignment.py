from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping

PlayerZone = Literal["p1", "p2"]
DetectionSource = Literal["normalized_x", "palm_center", "bbox_center", "center"]
DEFAULT_ZONE_SPLIT_X = 0.5
ZONE_WARN_BOTH_DETECTIONS_SAME_ZONE = "both_detections_in_same_zone"
ZONE_WARN_ALL_DETECTIONS_SAME_ZONE = "all_detections_in_same_zone"


@dataclass(frozen=True)
class ZoneAssignment:
    zone: PlayerZone
    normalized_x: float
    split_x: float
    source: DetectionSource

    def as_metadata(self) -> dict[str, Any]:
        return {
            "zone": self.zone,
            "normalized_x": self.normalized_x,
            "split_x": self.split_x,
            "source": self.source,
        }


def assign_zone(normalized_x: float, split_x: float = DEFAULT_ZONE_SPLIT_X) -> PlayerZone:
    x = _clamp_normalized(normalized_x)
    split = _clamp_normalized(split_x)
    return "p1" if x < split else "p2"


def assign_normalized_x(
    normalized_x: float,
    *,
    split_x: float = DEFAULT_ZONE_SPLIT_X,
    source: DetectionSource = "normalized_x",
) -> ZoneAssignment:
    x = _clamp_normalized(normalized_x)
    split = _clamp_normalized(split_x)
    return ZoneAssignment(zone="p1" if x < split else "p2", normalized_x=x, split_x=split, source=source)


def assign_hand(hand: Mapping[str, Any], *, split_x: float = DEFAULT_ZONE_SPLIT_X) -> ZoneAssignment:
    return assign_normalized_x(_point_x(hand, "palm_center"), split_x=split_x, source="palm_center")


def assign_face(face: Mapping[str, Any], *, split_x: float = DEFAULT_ZONE_SPLIT_X) -> ZoneAssignment:
    bbox = face.get("bbox")
    if isinstance(bbox, Mapping) and "x" in bbox and "width" in bbox:
        return assign_normalized_x(float(bbox["x"]) + float(bbox["width"]) / 2.0, split_x=split_x, source="bbox_center")
    return assign_normalized_x(_point_x(face, "center"), split_x=split_x, source="center")


def with_zone_assignment(detection: Mapping[str, Any], assignment: ZoneAssignment) -> dict[str, Any]:
    assigned = dict(detection)
    assigned["zone"] = assignment.zone
    assigned["zone_assignment"] = assignment.as_metadata()
    return assigned


def assign_hand_detection(hand: Mapping[str, Any], *, split_x: float = DEFAULT_ZONE_SPLIT_X) -> dict[str, Any]:
    return with_zone_assignment(hand, assign_hand(hand, split_x=split_x))


def assign_face_detection(face: Mapping[str, Any], *, split_x: float = DEFAULT_ZONE_SPLIT_X) -> dict[str, Any]:
    return with_zone_assignment(face, assign_face(face, split_x=split_x))


def assign_hand_detections(
    hands: Iterable[Mapping[str, Any]],
    *,
    split_x: float = DEFAULT_ZONE_SPLIT_X,
) -> list[dict[str, Any]]:
    return [assign_hand_detection(hand, split_x=split_x) for hand in hands]


def assign_face_detections(
    faces: Iterable[Mapping[str, Any]],
    *,
    split_x: float = DEFAULT_ZONE_SPLIT_X,
) -> list[dict[str, Any]]:
    return [assign_face_detection(face, split_x=split_x) for face in faces]


def summarize_zone_assignments(assignments: Iterable[ZoneAssignment]) -> dict[str, Any]:
    assignment_list = list(assignments)
    counts: dict[PlayerZone, int] = {"p1": 0, "p2": 0}
    for assignment in assignment_list:
        counts[assignment.zone] += 1

    present_zones = [zone for zone, count in counts.items() if count > 0]
    missing_zones = [zone for zone, count in counts.items() if count == 0]
    warnings: list[str] = []
    same_zone = len(assignment_list) >= 2 and len(present_zones) == 1
    if same_zone and len(assignment_list) == 2:
        warnings.append(ZONE_WARN_BOTH_DETECTIONS_SAME_ZONE)
    elif same_zone:
        warnings.append(ZONE_WARN_ALL_DETECTIONS_SAME_ZONE)

    split_x = assignment_list[0].split_x if assignment_list else DEFAULT_ZONE_SPLIT_X
    return {
        "split_x": split_x,
        "counts": counts,
        "missing_zones": missing_zones,
        "same_zone": same_zone,
        "warnings": warnings,
    }


def summarize_hand_assignments(
    hands: Iterable[Mapping[str, Any]],
    *,
    split_x: float = DEFAULT_ZONE_SPLIT_X,
) -> dict[str, Any]:
    return summarize_zone_assignments(assign_hand(hand, split_x=split_x) for hand in hands)


def summarize_face_assignments(
    faces: Iterable[Mapping[str, Any]],
    *,
    split_x: float = DEFAULT_ZONE_SPLIT_X,
) -> dict[str, Any]:
    return summarize_zone_assignments(assign_face(face, split_x=split_x) for face in faces)


def _point_x(detection: Mapping[str, Any], key: str) -> float:
    point = detection.get(key)
    if not isinstance(point, Mapping) or "x" not in point:
        raise ValueError(f"detection must include {key}.x for zone assignment")
    return float(point["x"])


def _clamp_normalized(value: float) -> float:
    x = float(value)
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x
