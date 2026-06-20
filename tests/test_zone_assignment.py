import unittest

from app.cv.zone_assignment import assign_zone


class ZoneAssignmentTests(unittest.TestCase):
    def test_assigns_left_side_to_p1(self) -> None:
        self.assertEqual(assign_zone(0.49), "p1")

    def test_assigns_split_and_right_side_to_p2(self) -> None:
        self.assertEqual(assign_zone(0.5), "p2")
        self.assertEqual(assign_zone(0.9), "p2")


if __name__ == "__main__":
    unittest.main()
