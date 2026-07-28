import unittest

from progress_ui import build_estimated_progress_html


class EstimatedProgressTests(unittest.TestCase):
    def test_progress_uses_elapsed_time_instead_of_fake_percentage_text(self):
        html = build_estimated_progress_html(60, is_dark_theme=True)

        self.assertIn("預估階段", html)
        self.assertIn('已等待 " + t + " 秒', html)
        self.assertNotIn('Math.floor(pct) + "%"', html)

    def test_progress_keeps_elapsed_timer_running_after_estimate(self):
        html = build_estimated_progress_html(60, is_dark_theme=False)

        self.assertIn("Gemini 仍在處理", html)
        self.assertNotIn("clearInterval", html)


if __name__ == "__main__":
    unittest.main()
