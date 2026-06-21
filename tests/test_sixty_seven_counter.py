import unittest

from app.cv.sixty_seven_counter import SixtySevenCounter


class SixtySevenCounterTests(unittest.TestCase):
    def test_counter_counts_extension_return_cycle(self) -> None:
        counter = SixtySevenCounter()

        self.assertEqual(counter.update(0.7), 0)
        self.assertEqual(counter.update(0.2), 1)

    def test_counter_counts_slow_extension_return_cycle(self) -> None:
        counter = SixtySevenCounter()

        for distance in [0.20, 0.24, 0.29, 0.34, 0.39, 0.43, 0.47]:
            counter.update(distance, now_ms=100)
        counter.update(0.24, now_ms=700)

        self.assertEqual(counter.reps, 1)

    def test_counter_tolerates_missing_intermediate_frames(self) -> None:
        counter = SixtySevenCounter()

        counter.update(0.36, now_ms=100)
        counter.update(0.29, now_ms=650)

        self.assertEqual(counter.reps, 1)

    def test_counter_counts_fast_vertical_hand_alternation(self) -> None:
        counter = SixtySevenCounter(cooldown_ms=0)
        left_high = [
            {"confidence": 0.9, "palm_center": {"x": 0.20, "y": 0.28}},
            {"confidence": 0.9, "palm_center": {"x": 0.28, "y": 0.68}},
        ]
        right_high = [
            {"confidence": 0.9, "palm_center": {"x": 0.20, "y": 0.68}},
            {"confidence": 0.9, "palm_center": {"x": 0.28, "y": 0.28}},
        ]

        counter.update_from_hands(left_high, now_ms=100, frame_timestamp_ms=100)
        counter.update_from_hands(right_high, now_ms=180, frame_timestamp_ms=180)
        counter.update_from_hands(left_high, now_ms=260, frame_timestamp_ms=260)

        self.assertEqual(counter.reps, 2)

    def test_fast_motion_continues_scoring_between_cv_frames(self) -> None:
        counter = SixtySevenCounter(cooldown_ms=0)
        left_high = [
            {"confidence": 0.9, "palm_center": {"x": 0.20, "y": 0.28}},
            {"confidence": 0.9, "palm_center": {"x": 0.28, "y": 0.68}},
        ]
        right_high = [
            {"confidence": 0.9, "palm_center": {"x": 0.20, "y": 0.68}},
            {"confidence": 0.9, "palm_center": {"x": 0.28, "y": 0.28}},
        ]

        counter.update_from_hands(left_high, now_ms=100, frame_timestamp_ms=100)
        counter.update_from_hands(right_high, now_ms=180, frame_timestamp_ms=180)
        first_rate = counter.score_rate
        counter.tick(16)
        first_score = counter.display_score
        counter.tick(16)

        self.assertGreater(first_rate, 0)
        self.assertGreater(first_score, 0)
        self.assertGreater(counter.display_score, first_score)

    def test_static_hands_do_not_accumulate_motion_score(self) -> None:
        counter = SixtySevenCounter(cooldown_ms=0)
        hands = [
            {"confidence": 0.9, "palm_center": {"x": 0.20, "y": 0.40}},
            {"confidence": 0.9, "palm_center": {"x": 0.28, "y": 0.62}},
        ]

        counter.update_from_hands(hands, now_ms=100, frame_timestamp_ms=100)
        counter.update_from_hands(hands, now_ms=180, frame_timestamp_ms=180)
        counter.tick(16)

        self.assertEqual(counter.display_score, 0)

    def test_counter_rejects_tiny_vertical_alternation_jitter(self) -> None:
        counter = SixtySevenCounter(cooldown_ms=0)
        almost_level = [
            {"confidence": 0.9, "palm_center": {"x": 0.20, "y": 0.49}},
            {"confidence": 0.9, "palm_center": {"x": 0.28, "y": 0.53}},
        ]
        almost_level_flipped = [
            {"confidence": 0.9, "palm_center": {"x": 0.20, "y": 0.53}},
            {"confidence": 0.9, "palm_center": {"x": 0.28, "y": 0.49}},
        ]

        counter.update_from_hands(almost_level, now_ms=100, frame_timestamp_ms=100)
        counter.update_from_hands(almost_level_flipped, now_ms=180, frame_timestamp_ms=180)
        counter.update_from_hands(almost_level, now_ms=260, frame_timestamp_ms=260)

        self.assertEqual(counter.reps, 0)

    def test_counter_rejects_tiny_threshold_jitter(self) -> None:
        counter = SixtySevenCounter(cooldown_ms=0)

        for distance in [0.35, 0.32, 0.34, 0.31, 0.35, 0.32]:
            counter.update(distance, now_ms=100)

        self.assertEqual(counter.reps, 0)

    def test_counter_rejects_small_jitter(self) -> None:
        counter = SixtySevenCounter(min_delta=0.08)

        for distance in [0.20, 0.23, 0.19, 0.24, 0.21]:
            counter.update(distance, now_ms=100)

        self.assertEqual(counter.reps, 0)
        self.assertEqual(counter.state, "neutral")

    def test_counter_ignores_stale_frames(self) -> None:
        counter = SixtySevenCounter(stale_after_ms=250)
        hands = [
            {"confidence": 0.9, "palm_center": {"x": 0.1, "y": 0.5}},
            {"confidence": 0.9, "palm_center": {"x": 0.8, "y": 0.5}},
        ]

        counter.update_from_hands(hands, now_ms=1_000, frame_timestamp_ms=700)

        self.assertEqual(counter.reps, 0)
        self.assertTrue(counter.stale)

        counter.update_from_hands(hands, now_ms=1_000, frame_timestamp_ms=1_000)

        self.assertFalse(counter.stale)

    def test_counter_enforces_cooldown(self) -> None:
        counter = SixtySevenCounter(cooldown_ms=500)

        counter.update(0.1, now_ms=0)
        counter.update(0.6, now_ms=100)
        counter.update(0.1, now_ms=200)
        counter.update(0.6, now_ms=300)
        counter.update(0.1, now_ms=400)

        self.assertEqual(counter.reps, 1)

    def test_counter_uses_two_zone_hands(self) -> None:
        counter = SixtySevenCounter(cooldown_ms=0)
        close = [
            {"confidence": 0.9, "palm_center": {"x": 0.20, "y": 0.5}},
            {"confidence": 0.9, "palm_center": {"x": 0.26, "y": 0.5}},
        ]
        far = [
            {"confidence": 0.9, "palm_center": {"x": 0.05, "y": 0.5}},
            {"confidence": 0.9, "palm_center": {"x": 0.55, "y": 0.5}},
        ]

        counter.update_from_hands(close, now_ms=100, frame_timestamp_ms=100)
        counter.update_from_hands(far, now_ms=200, frame_timestamp_ms=200)
        counter.update_from_hands(close, now_ms=300, frame_timestamp_ms=300)

        self.assertEqual(counter.reps, 1)

    def test_counter_uses_farthest_detected_hand_pair(self) -> None:
        counter = SixtySevenCounter(cooldown_ms=0)
        far_with_extra_hand = [
            {"confidence": 0.9, "palm_center": {"x": 0.10, "y": 0.5}},
            {"confidence": 0.9, "palm_center": {"x": 0.18, "y": 0.5}},
            {"confidence": 0.9, "palm_center": {"x": 0.46, "y": 0.5}},
        ]
        close = [
            {"confidence": 0.9, "palm_center": {"x": 0.20, "y": 0.5}},
            {"confidence": 0.9, "palm_center": {"x": 0.27, "y": 0.5}},
        ]

        counter.update_from_hands(far_with_extra_hand, now_ms=100, frame_timestamp_ms=100)
        counter.update_from_hands(close, now_ms=200, frame_timestamp_ms=200)

        self.assertEqual(counter.reps, 1)


if __name__ == "__main__":
    unittest.main()
