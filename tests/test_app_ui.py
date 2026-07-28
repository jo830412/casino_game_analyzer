import unittest

from streamlit.testing.v1 import AppTest


def make_history_record():
    return {
        "time": "2026/07/28 12:34",
        "project_name": "測試專案",
        "analyst_name": "Amy",
        "game_type": "Slot 老虎機",
        "analysis_modes": ["爽感與節奏"],
        "model": "gemini-2.5-flash",
        "report_md": "測試報告",
        "styled_html": "<p>測試報告</p>",
    }


class ReportContextTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file("app.py", default_timeout=20)
        self.app.session_state["analysis_history"] = [make_history_record()]
        self.app.run()

    def test_saved_report_is_visibly_distinguished_from_current_form(self):
        markdown_values = [item.value for item in self.app.markdown]
        caption_values = [item.value for item in self.app.caption]

        self.assertIn("## 📊 目前顯示的分析報告", markdown_values)
        self.assertIn(
            "🗂️ 歷史紀錄 · 分析時間：2026/07/28 12:34",
            caption_values,
        )

    def test_summary_and_history_use_friendly_model_names(self):
        markdown_values = [item.value for item in self.app.markdown]
        caption_values = [item.value for item in self.app.caption]

        self.assertIn(
            "**模型**：Gemini 3.5 Flash（推薦）",
            markdown_values,
        )
        self.assertIn(
            "模型：Gemini 2.5 Flash（省成本）",
            caption_values,
        )


if __name__ == "__main__":
    unittest.main()
