import unittest

from app.cv.sixty_seven_counter import SixtySevenCounter


class SixtySevenCounterTests(unittest.TestCase):
    def test_counter_counts_extension_return_cycle(self) -> None:
        counter = SixtySevenCounter()

        self.assertEqual(counter.update(0.7), 0)
        self.assertEqual(counter.update(0.2), 1)


if __name__ == "__main__":
    unittest.main()
