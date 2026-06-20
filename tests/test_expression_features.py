import unittest

from app.cv.expression_features import classify_expression, extract_expression_features
from app.games.emoji_face_match import build_expression_sequence, evaluate_match


class ExpressionFeatureTests(unittest.TestCase):
    def test_classifies_supported_mvp_expressions(self) -> None:
        self.assertEqual(classify_expression({"smile": 0.8}), "smile")
        self.assertEqual(classify_expression({"mouth_open": 0.8}), "surprised")
        self.assertEqual(classify_expression({"left_eye_closed": 0.9, "right_eye_closed": 0.88}), "eyes_closed")
        self.assertEqual(classify_expression({"left_eye_closed": 0.9, "right_eye_closed": 0.1}), "wink")
        self.assertEqual(classify_expression({}), "neutral")

    def test_extracts_explicit_face_expression_features(self) -> None:
        features = extract_expression_features({"expression_features": {"smile": 1.2, "mouth_open": "bad"}})

        self.assertEqual(features["smile"], 1.0)
        self.assertEqual(features["mouth_open"], 0.0)

    def test_extracts_named_landmark_features(self) -> None:
        features = extract_expression_features(
            {
                "landmarks": {
                    "mouth_left": {"x": 0.2, "y": 0.5},
                    "mouth_right": {"x": 0.8, "y": 0.5},
                    "upper_lip": {"x": 0.5, "y": 0.48},
                    "lower_lip": {"x": 0.5, "y": 0.52},
                    "left_eye_top": {"x": 0.35, "y": 0.3},
                    "left_eye_bottom": {"x": 0.35, "y": 0.31},
                    "right_eye_top": {"x": 0.65, "y": 0.3},
                    "right_eye_bottom": {"x": 0.65, "y": 0.31},
                }
            }
        )

        self.assertGreater(features["smile"], 0.6)

    def test_evaluates_match_points(self) -> None:
        result = evaluate_match("smile", {"smile": 0.8})

        self.assertTrue(result.hit)
        self.assertEqual(result.points, 100)

    def test_expression_sequence_is_deterministic_without_immediate_repeats(self) -> None:
        sequence = build_expression_sequence("session-1", 12)

        self.assertEqual(sequence, build_expression_sequence("session-1", 12))
        self.assertTrue(all(left != right for left, right in zip(sequence, sequence[1:])))


if __name__ == "__main__":
    unittest.main()
