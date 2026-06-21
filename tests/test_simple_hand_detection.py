from __future__ import annotations

import unittest

from app.cv.simple_hand_detection import SimpleHandDetectionService


class SimpleHandDetectionTests(unittest.TestCase):
    def test_static_upper_face_blob_is_not_preferred_over_moving_hands(self) -> None:
        try:
            import cv2
            import numpy as np
        except Exception as exc:  # pragma: no cover - optional local dependency
            self.skipTest(f"OpenCV/NumPy unavailable: {exc}")

        skin_bgr = cv2.cvtColor(np.uint8([[[160, 150, 110]]]), cv2.COLOR_YCrCb2BGR)[0, 0].tolist()

        def frame(hand_offset: int) -> object:
            image = np.zeros((180, 320, 3), dtype=np.uint8)
            cv2.ellipse(image, (80, 48), (28, 38), 0, 0, 360, skin_bgr, -1)
            cv2.ellipse(image, (240, 48), (28, 38), 0, 0, 360, skin_bgr, -1)
            cv2.circle(image, (42 + hand_offset, 125), 22, skin_bgr, -1)
            cv2.circle(image, (126 - hand_offset, 128), 22, skin_bgr, -1)
            cv2.circle(image, (194 + hand_offset, 125), 22, skin_bgr, -1)
            cv2.circle(image, (286 - hand_offset, 128), 22, skin_bgr, -1)
            return image

        service = SimpleHandDetectionService(max_hands=4, split_x=0.5)
        first = service.detect(frame(0))
        second = service.detect(frame(12))

        self.assertEqual(len(first), 4)
        self.assertEqual(len(second), 4)
        self.assertTrue(all(float(hand["palm_center"]["y"]) > 0.55 for hand in second))
        self.assertEqual([hand["zone"] for hand in second].count("p1"), 2)
        self.assertEqual([hand["zone"] for hand in second].count("p2"), 2)


if __name__ == "__main__":
    unittest.main()
