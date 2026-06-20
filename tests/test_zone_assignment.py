import unittest

from app.cv.zone_assignment import (
    ZONE_WARN_BOTH_DETECTIONS_SAME_ZONE,
    assign_face,
    assign_face_detection,
    assign_hand,
    assign_hand_detection,
    assign_zone,
    summarize_face_assignments,
)


class ZoneAssignmentTests(unittest.TestCase):
    def test_default_split_assigns_left_side_to_p1(self) -> None:
        self.assertEqual(assign_zone(0.49), "p1")

    def test_default_split_assigns_split_and_right_side_to_p2(self) -> None:
        self.assertEqual(assign_zone(0.5), "p2")
        self.assertEqual(assign_zone(0.9), "p2")

    def test_custom_split_controls_boundary(self) -> None:
        self.assertEqual(assign_zone(0.59, split_x=0.6), "p1")
        self.assertEqual(assign_zone(0.6, split_x=0.6), "p2")

    def test_normalized_x_is_clamped_before_assignment(self) -> None:
        self.assertEqual(assign_zone(-0.2), "p1")
        self.assertEqual(assign_zone(1.4), "p2")

    def test_hand_assignment_uses_palm_center(self) -> None:
        hand = {"hand_id": "left", "palm_center": {"x": 0.24, "y": 0.5}}

        assignment = assign_hand(hand)
        assigned_hand = assign_hand_detection(hand)

        self.assertEqual(assignment.zone, "p1")
        self.assertEqual(assignment.source, "palm_center")
        self.assertEqual(assigned_hand["zone"], "p1")
        self.assertEqual(assigned_hand["zone_assignment"]["normalized_x"], 0.24)

    def test_face_assignment_uses_bounding_box_center(self) -> None:
        face = {"face_id": "right", "bbox": {"x": 0.54, "y": 0.2, "width": 0.18, "height": 0.3}}

        assignment = assign_face(face)
        assigned_face = assign_face_detection(face)

        self.assertEqual(assignment.zone, "p2")
        self.assertEqual(assignment.source, "bbox_center")
        self.assertAlmostEqual(assignment.normalized_x, 0.63)
        self.assertEqual(assigned_face["zone_assignment"]["source"], "bbox_center")

    def test_face_assignment_can_fall_back_to_center_point(self) -> None:
        face = {"face_id": "centered", "center": {"x": 0.4, "y": 0.2}}

        assignment = assign_face(face)

        self.assertEqual(assignment.zone, "p1")
        self.assertEqual(assignment.source, "center")

    def test_summary_warns_when_two_faces_are_in_the_same_zone(self) -> None:
        summary = summarize_face_assignments(
            [
                {"face_id": "a", "bbox": {"x": 0.05, "y": 0.2, "width": 0.1, "height": 0.2}},
                {"face_id": "b", "bbox": {"x": 0.3, "y": 0.2, "width": 0.1, "height": 0.2}},
            ]
        )

        self.assertEqual(summary["counts"], {"p1": 2, "p2": 0})
        self.assertEqual(summary["missing_zones"], ["p2"])
        self.assertTrue(summary["same_zone"])
        self.assertIn(ZONE_WARN_BOTH_DETECTIONS_SAME_ZONE, summary["warnings"])


if __name__ == "__main__":
    unittest.main()
