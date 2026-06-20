import unittest

from app.cv.expression_features import classify_expression


class ExpressionFeatureTests(unittest.TestCase):
    def test_classifies_simple_expression_features(self) -> None:
        self.assertEqual(classify_expression({"smile": 0.8}), "smile")
        self.assertEqual(classify_expression({}), "neutral")


if __name__ == "__main__":
    unittest.main()
