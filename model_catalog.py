MODEL_LABELS = {
    "gemini-3.5-flash": "Gemini 3.5 Flash（推薦）",
    "gemini-3-flash-preview": "Gemini 3 Flash Preview（較低成本／預覽版）",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview（高品質／付費）",
    "gemini-2.5-flash": "Gemini 2.5 Flash（省成本）",
    "gemini-2.5-pro": "Gemini 2.5 Pro（舊版高品質）",
}

MODEL_IDS = list(MODEL_LABELS)


def model_display_name(model_id):
    return MODEL_LABELS.get(model_id, model_id)
