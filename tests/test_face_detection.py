import unittest
from types import SimpleNamespace

from app.cv.expression_features import classify_expression, extract_expression_features
from app.cv.face_detection import _face_from_landmarks


class FaceDetectionTests(unittest.TestCase):
    def test_face_mesh_landmarks_feed_expression_features(self) -> None:
        landmarks = [SimpleNamespace(x=0.45 + (index % 8) * 0.01, y=0.35 + (index % 6) * 0.01) for index in range(478)]
        landmarks[61] = SimpleNamespace(x=0.35, y=0.50)
        landmarks[291] = SimpleNamespace(x=0.65, y=0.50)
        landmarks[13] = SimpleNamespace(x=0.50, y=0.535)
        landmarks[14] = SimpleNamespace(x=0.50, y=0.565)
        landmarks[33] = SimpleNamespace(x=0.36, y=0.40)
        landmarks[133] = SimpleNamespace(x=0.46, y=0.40)
        landmarks[159] = SimpleNamespace(x=0.42, y=0.40)
        landmarks[145] = SimpleNamespace(x=0.42, y=0.42)
        landmarks[362] = SimpleNamespace(x=0.54, y=0.40)
        landmarks[263] = SimpleNamespace(x=0.64, y=0.40)
        landmarks[386] = SimpleNamespace(x=0.58, y=0.40)
        landmarks[374] = SimpleNamespace(x=0.58, y=0.42)

        face = _face_from_landmarks(0, landmarks)
        features = extract_expression_features(face)

        self.assertIn("mouth_left", face["landmarks"])
        self.assertGreater(face["bbox"]["height"], 0.0)
        self.assertEqual(classify_expression(features), "smile")


if __name__ == "__main__":
    unittest.main()
