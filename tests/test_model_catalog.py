import unittest

from model_catalog import MODEL_IDS, model_display_name


class ModelCatalogTests(unittest.TestCase):
    def test_model_ids_preserve_supported_provider_values(self):
        self.assertEqual(
            [
                "gemini-3.5-flash",
                "gemini-3-flash-preview",
                "gemini-3.1-pro-preview",
                "gemini-2.5-flash",
                "gemini-2.5-pro",
            ],
            MODEL_IDS,
        )

    def test_model_ids_have_clear_user_facing_labels(self):
        self.assertEqual(
            "Gemini 3.5 Flash（推薦）",
            model_display_name("gemini-3.5-flash"),
        )
        self.assertEqual(
            "Gemini 3 Flash Preview（較低成本／預覽版）",
            model_display_name("gemini-3-flash-preview"),
        )
        self.assertEqual(
            "Gemini 3.1 Pro Preview（高品質／付費）",
            model_display_name("gemini-3.1-pro-preview"),
        )
        self.assertEqual(
            "Gemini 2.5 Flash（省成本）",
            model_display_name("gemini-2.5-flash"),
        )
        self.assertEqual(
            "Gemini 2.5 Pro（舊版高品質）",
            model_display_name("gemini-2.5-pro"),
        )

    def test_unknown_historical_model_keeps_its_original_id(self):
        self.assertEqual(
            "gemini-retired-model",
            model_display_name("gemini-retired-model"),
        )


if __name__ == "__main__":
    unittest.main()
