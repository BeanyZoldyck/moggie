import unittest

from app.cv.sixty_seven_counter import SixtySevenCounter


class SixtySevenCounterTests(unittest.TestCase):
    def test_counter_counts_extension_return_cycle(self) -> None:
        counter = SixtySevenCounter()

        self.assertEqual(counter.update(0.7), 0)
        self.assertEqual(counter.update(0.2), 1)

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


if __name__ == "__main__":
    unittest.main()
