import unittest
import math
from pathlib import Path

from analyze_scores import category_priority, pack_priority_circles, parse_html, solid_score_color


class ScoreAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.courses = parse_html(Path("北大树洞.html"))

    def test_expected_page_shape(self):
        self.assertEqual(len(self.courses), 54)
        self.assertEqual(len({c.semester for c in self.courses}), 6)
        # The source page legitimately contains one zero-credit pass/fail course.
        self.assertTrue(all(c.name and c.credits >= 0 and c.category for c in self.courses))

    def test_special_scores_are_not_numeric(self):
        special = [c for c in self.courses if c.score_text in {"合格", "W"}]
        self.assertTrue(special)
        self.assertTrue(all(c.score is None for c in special))

    def test_passed_courses_exist_for_green_rendering(self):
        passed = [c for c in self.courses if c.score_text in {"合格", "通过"}]
        self.assertTrue(passed)

    def test_priority_order_and_circle_packing(self):
        visible = [c for c in self.courses if c.score is not None or c.score_text in {"合格", "通过"}]
        packed = pack_priority_circles(visible)
        self.assertEqual(category_priority(packed[0][0]), 3)
        circles = [circle for _, circle in packed]
        for index, (x, y, radius) in enumerate(circles):
            for other_x, other_y, other_radius in circles[index + 1:]:
                self.assertGreaterEqual(
                    math.hypot(x - other_x, y - other_y),
                    radius + other_radius + 5.0 - 1e-6,
                )

    def test_gradient_moves_from_red_toward_green(self):
        low = solid_score_color(60)
        high = solid_score_color(99)
        self.assertGreater(low[0], low[1])
        self.assertGreater(high[1], high[0])


if __name__ == "__main__":
    unittest.main()
