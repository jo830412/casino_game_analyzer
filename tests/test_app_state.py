import unittest

from app_state import (
    apply_options_transactionally,
    persist_analysis_record,
    switch_theme,
)


class ThemeStateTests(unittest.TestCase):
    def test_switch_theme_applies_native_theme_before_committing_session_state(self):
        state = {"ui_theme": "dark"}
        calls = []

        def apply_theme(theme_name):
            calls.append((theme_name, dict(state)))

        result = switch_theme(state, apply_theme)

        self.assertEqual("light", result)
        self.assertEqual([("light", {"ui_theme": "dark"})], calls)
        self.assertEqual("light", state["ui_theme"])
        self.assertTrue(state["theme_live_override"])
        self.assertNotIn("theme_native_sync_error", state)

    def test_switch_theme_falls_back_to_css_when_native_sync_fails(self):
        state = {"ui_theme": "dark"}

        def apply_theme(_theme_name):
            raise RuntimeError("private API unavailable")

        result = switch_theme(state, apply_theme)

        self.assertEqual("light", result)
        self.assertEqual("light", state["ui_theme"])
        self.assertTrue(state["theme_live_override"])
        self.assertEqual(
            "private API unavailable",
            state["theme_native_sync_error"],
        )

    def test_apply_options_rolls_back_partial_native_theme_update(self):
        values = {"theme.base": "dark", "theme.textColor": "#fff"}
        set_calls = []

        def get_option(name):
            return values[name]

        def set_option(name, value):
            set_calls.append((name, value))
            values[name] = value
            if name == "theme.textColor" and value == "#111":
                raise RuntimeError("unsupported option")

        with self.assertRaisesRegex(RuntimeError, "unsupported option"):
            apply_options_transactionally(
                {
                    "theme.base": "light",
                    "theme.textColor": "#111",
                },
                get_option,
                set_option,
            )

        self.assertEqual(
            {"theme.base": "dark", "theme.textColor": "#fff"},
            values,
        )
        self.assertEqual(
            [
                ("theme.base", "light"),
                ("theme.textColor", "#111"),
                ("theme.textColor", "#fff"),
                ("theme.base", "dark"),
            ],
            set_calls,
        )


class AnalysisHistoryStateTests(unittest.TestCase):
    def test_persist_failure_does_not_commit_history_or_success_flag(self):
        original = {"id": "old"}
        state = {"analysis_history": [original]}

        def save_history(_history):
            raise OSError("disk full")

        with self.assertRaisesRegex(OSError, "disk full"):
            persist_analysis_record(
                state,
                {"id": "new"},
                save_history,
                max_items=50,
            )

        self.assertEqual([original], state["analysis_history"])
        self.assertNotIn("just_analyzed", state)

    def test_persist_saves_before_committing_history_and_success_flag(self):
        state = {"analysis_history": [{"id": "old"}]}
        observed = []

        def save_history(history):
            observed.append(list(history))
            self.assertEqual([{"id": "old"}], state["analysis_history"])
            self.assertNotIn("just_analyzed", state)

        result = persist_analysis_record(
            state,
            {"id": "new"},
            save_history,
            max_items=2,
        )

        expected = [{"id": "old"}, {"id": "new"}]
        self.assertEqual([expected], observed)
        self.assertEqual(expected, result)
        self.assertEqual(expected, state["analysis_history"])
        self.assertTrue(state["just_analyzed"])


if __name__ == "__main__":
    unittest.main()
