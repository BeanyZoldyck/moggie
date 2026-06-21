import unittest

from app.cv.expression_features import classify_expression, extract_expression_features
from app.games.emoji_face_match import SUPPORTED_EXPRESSIONS, build_expression_sequence, evaluate_match, expression_glyph


class ExpressionFeatureTests(unittest.TestCase):
    def test_classifies_supported_mvp_expressions(self) -> None:
        self.assertEqual(classify_expression({"smile": 0.8}), "smile")
        self.assertEqual(classify_expression({"mouth_open": 0.8}), "surprised")
        self.assertEqual(classify_expression({"tongue_out": 0.8, "mouth_open": 0.9}), "tongue_out")
        self.assertEqual(classify_expression({"tongue_out": 0.8, "mouth_open": 0.1}), "neutral")
        self.assertEqual(classify_expression({"left_eye_closed": 0.9, "right_eye_closed": 0.1}), "wink")
        self.assertEqual(classify_expression({"look_left": 0.8}), "look_left")
        self.assertEqual(classify_expression({"look_right": 0.8}), "look_right")
        self.assertEqual(classify_expression({}), "neutral")

    def test_extracts_explicit_face_expression_features(self) -> None:
        features = extract_expression_features({"expression_features": {"smile": 1.2, "mouth_open": "bad"}})

        self.assertEqual(features["smile"], 1.0)
        self.assertEqual(features["mouth_open"], 0.0)
        self.assertEqual(features["tongue_out"], 0.0)

    def test_extracts_named_landmark_features(self) -> None:
        features = extract_expression_features(
            {
                "landmarks": {
                    "mouth_left": {"x": 0.2, "y": 0.5},
                    "mouth_right": {"x": 0.8, "y": 0.5},
                    "upper_lip": {"x": 0.5, "y": 0.56},
                    "lower_lip": {"x": 0.5, "y": 0.60},
                    "left_eye_outer": {"x": 0.28, "y": 0.3},
                    "left_eye_inner": {"x": 0.42, "y": 0.3},
                    "left_eye_top": {"x": 0.35, "y": 0.3},
                    "left_eye_bottom": {"x": 0.35, "y": 0.31},
                    "right_eye_inner": {"x": 0.58, "y": 0.3},
                    "right_eye_outer": {"x": 0.72, "y": 0.3},
                    "right_eye_top": {"x": 0.65, "y": 0.3},
                    "right_eye_bottom": {"x": 0.65, "y": 0.31},
                    "left_cheek": {"x": 0.16, "y": 0.44},
                    "right_cheek": {"x": 0.84, "y": 0.44},
                    "nose_tip": {"x": 0.5, "y": 0.42},
                }
            }
        )

        self.assertGreater(features["smile"], 0.6)
        self.assertLess(features["mouth_open"], 0.4)
        self.assertLess(features["look_left"], 0.2)
        self.assertLess(features["look_right"], 0.2)

    def test_extracts_look_direction_from_nose_offset(self) -> None:
        base_landmarks = {
            "mouth_left": {"x": 0.30, "y": 0.55},
            "mouth_right": {"x": 0.70, "y": 0.55},
            "upper_lip": {"x": 0.5, "y": 0.50},
            "lower_lip": {"x": 0.5, "y": 0.54},
            "left_eye_outer": {"x": 0.28, "y": 0.34},
            "left_eye_inner": {"x": 0.42, "y": 0.34},
            "left_eye_top": {"x": 0.35, "y": 0.33},
            "left_eye_bottom": {"x": 0.35, "y": 0.36},
            "right_eye_inner": {"x": 0.58, "y": 0.34},
            "right_eye_outer": {"x": 0.72, "y": 0.34},
            "right_eye_top": {"x": 0.65, "y": 0.33},
            "right_eye_bottom": {"x": 0.65, "y": 0.36},
            "left_cheek": {"x": 0.18, "y": 0.45},
            "right_cheek": {"x": 0.82, "y": 0.45},
        }

        left_features = extract_expression_features({"landmarks": {**base_landmarks, "nose_tip": {"x": 0.40, "y": 0.43}}})
        right_features = extract_expression_features({"landmarks": {**base_landmarks, "nose_tip": {"x": 0.60, "y": 0.43}}})

        self.assertGreater(left_features["look_left"], 0.6)
        self.assertLess(left_features["look_right"], 0.2)
        self.assertGreater(right_features["look_right"], 0.6)
        self.assertLess(right_features["look_left"], 0.2)
        self.assertEqual(classify_expression(left_features), "look_left")
        self.assertEqual(classify_expression(right_features), "look_right")

    def test_explicit_tongue_feature_merges_with_landmark_features(self) -> None:
        features = extract_expression_features(
            {
                "expression_features": {"tongue_out": 0.9},
                "landmarks": {
                    "mouth_left": {"x": 0.2, "y": 0.5},
                    "mouth_right": {"x": 0.8, "y": 0.5},
                    "upper_lip": {"x": 0.5, "y": 0.44},
                    "lower_lip": {"x": 0.5, "y": 0.58},
                },
            }
        )

        self.assertEqual(classify_expression(features), "tongue_out")

    def test_evaluates_match_points(self) -> None:
        result = evaluate_match("smile", {"smile": 0.8})

        self.assertTrue(result.hit)
        self.assertEqual(result.points, 100)

    def test_target_specific_judging_ignores_noisy_tongue_for_smile_and_surprise(self) -> None:
        noisy_smile = evaluate_match("smile", {"smile": 0.8, "tongue_out": 0.8, "mouth_open": 0.35})
        noisy_surprise = evaluate_match("surprised", {"mouth_open": 0.8, "tongue_out": 0.8})

        self.assertTrue(noisy_smile.hit)
        self.assertTrue(noisy_surprise.hit)

    def test_deadpan_requires_low_expression_activity(self) -> None:
        self.assertTrue(evaluate_match("neutral", {"smile": 0.1, "mouth_open": 0.1}).hit)
        self.assertFalse(evaluate_match("neutral", {"smile": 0.7}).hit)
        self.assertFalse(evaluate_match("neutral", {"tongue_out": 0.8, "mouth_open": 0.4}).hit)
        self.assertFalse(evaluate_match("neutral", {"look_left": 0.8}).hit)

    def test_tongue_out_requires_tongue_and_open_mouth(self) -> None:
        self.assertFalse(evaluate_match("tongue_out", {"tongue_out": 0.9, "mouth_open": 0.1}).hit)
        self.assertTrue(evaluate_match("tongue_out", {"tongue_out": 0.9, "mouth_open": 0.5}).hit)

    def test_expression_sequence_is_deterministic_without_immediate_repeats(self) -> None:
        sequence = build_expression_sequence("session-1", 12)

        self.assertEqual(sequence, build_expression_sequence("session-1", 12))
        self.assertTrue(all(left != right for left, right in zip(sequence, sequence[1:])))
        self.assertNotIn("eyes_closed", sequence)
        self.assertTrue(set(sequence) <= set(SUPPORTED_EXPRESSIONS))
        self.assertEqual(expression_glyph("look_left"), "L")
        self.assertEqual(expression_glyph("look_right"), "R")


if __name__ == "__main__":
    unittest.main()
