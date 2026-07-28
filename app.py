import streamlit as st
from google import genai
from google.genai import types
import tempfile
import os
import time
import pathlib
import json
import re
import html as html_lib
import markdown as md_lib
from datetime import datetime

from app_state import (
    apply_options_transactionally,
    persist_analysis_record,
    switch_theme,
)
from model_catalog import MODEL_IDS, model_display_name
from progress_ui import build_estimated_progress_html

APP_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
HISTORY_FILE = DATA_DIR / "analysis_history.json"
MAX_HISTORY_ITEMS = 50
RECOMMENDED_TOTAL_MB = 250
HIGH_RISK_TOTAL_MB = 500

ANALYSIS_MODE_GUIDES = {
    "爽感與節奏": "聚焦 Spin/發牌速度、連押順暢度、中獎前等待、爆分節奏、玩家爽感高低差。",
    "UI/UX 操作": "聚焦押注、Spin、Auto、餘額、贏分、返回與設定等操作是否直覺，並指出可能誤觸或看不懂的位置。",
    "美術特效": "聚焦符號辨識度、粒子、轉場、大獎演出、畫面層級、長時間觀看疲勞與主題一致性。",
    "音效層次": "聚焦按鈕音、中獎音、大獎音樂、音效堆疊、情緒轉折與是否有記憶點。",
    "新手理解": "聚焦第一次玩的玩家能否理解規則、獎勵、Bonus/Free Game 觸發條件與下一步行動。",
    "版本驗收": "聚焦是否能轉成下一版驗收項目，列出可測試的改動、驗收標準與風險。",
}

SEGMENT_TYPES = ["一般 Spin", "中小獎", "Big Win", "Free Game", "Bonus 轉場", "UI 操作", "其他"]


def format_seconds(total_seconds):
    minutes = int(total_seconds) // 60
    seconds = int(total_seconds) % 60
    return f"{minutes:02d}:{seconds:02d}"


def format_file_size(size_bytes):
    if not size_bytes:
        return "0 MB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def estimate_analysis_seconds(total_size_mb):
    return max(30, min(150, int(total_size_mb * 3 + 30)))


def extract_task_cards(report_text):
    match = re.search(r'##\s*📝\s*7\.\s*可直接建立的任務卡([\s\S]*?)(?=\n---\n|\n##\s*📊|$)', report_text)
    if not match:
        return "報告中未偵測到「可直接建立的任務卡」區塊。"
    return match.group(1).strip()


def get_secret_value(key, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


def load_analysis_history():
    if not HISTORY_FILE.exists():
        return []
    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_analysis_history(history):
    DATA_DIR.mkdir(exist_ok=True)
    safe_history = history[-MAX_HISTORY_ITEMS:]
    with HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump(safe_history, f, ensure_ascii=False, indent=2)


def trigger_analysis():
    st.session_state["is_analyzing"] = True
    st.session_state["analysis_done"] = False


# 深淺色主題：Streamlit 尚無官方執行時切換 API。
# 作法：1) st._config.set_option 寫入主題設定，讓「下一次頁面載入」原生套用；
#      2) 因為新版 Streamlit 前端不會在 rerun 時即時吃新主題，切換當下另外注入
#         覆蓋 CSS（見 build_theme_override_css），讓主要畫面立即變色；
#         使用者重新整理頁面後會回到 100% 原生主題渲染。
# 注意：set_option 為整個伺服器行程共用，多人同用一個部署時會互相影響預設主題。
THEME_PRESETS = {
    "dark": {
        "theme.base": "dark",
        "theme.primaryColor": "#FFC107",
        "theme.backgroundColor": "#0E1117",
        "theme.secondaryBackgroundColor": "#262730",
        "theme.textColor": "#FAFAFA",
    },
    "light": {
        "theme.base": "light",
        "theme.primaryColor": "#D97706",
        "theme.backgroundColor": "#FFFFFF",
        "theme.secondaryBackgroundColor": "#F0F2F6",
        "theme.textColor": "#31333F",
    },
}


def detect_theme_base():
    # 以伺服器目前的 theme.base 設定為準（與切換按鈕寫入的是同一個來源），
    # 避免第一次載入時 st.context.theme 回報值與實際畫面不一致。
    try:
        base = st._config.get_option("theme.base")
        if base in ("dark", "light"):
            return base
    except Exception:
        pass
    return "dark"


def apply_theme(theme_name):
    apply_options_transactionally(
        THEME_PRESETS[theme_name],
        st._config.get_option,
        st._config.set_option,
    )


def toggle_theme():
    switch_theme(st.session_state, apply_theme)


def build_theme_override_css(theme_name):
    """同一個 session 內切換主題時的即時覆蓋樣式（重新整理後由原生主題接手）。"""
    preset = THEME_PRESETS[theme_name]
    bg = preset["theme.backgroundColor"]
    bg2 = preset["theme.secondaryBackgroundColor"]
    text = preset["theme.textColor"]
    border = "#3D4044" if theme_name == "dark" else "#D6D6D9"
    return f"""
<style>
[data-testid="stApp"], [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
    background-color: {bg} !important;
}}
[data-testid="stSidebar"], [data-testid="stSidebarContent"] {{
    background-color: {bg2} !important;
}}
[data-testid="stApp"] :is(h1, h2, h3, h4, h5, h6) {{ color: {text} !important; }}
[data-testid="stApp"] [data-testid="stMarkdownContainer"]
  :is(p, li, td, th, strong, em, span):not([data-testid="stAlert"] *, button *, a, a *) {{
    color: {text} !important;
}}
[data-testid="stApp"] [data-testid="stCaptionContainer"] :is(p, span):not([data-testid="stAlert"] *) {{
    color: {text} !important;
}}
[data-testid="stMetricValue"], [data-testid="stMetricLabel"] {{ color: {text} !important; }}
[data-baseweb="tab"] {{ color: {text} !important; }}
button[data-testid="stBaseButton-secondary"] {{
    background-color: {bg2} !important; color: {text} !important; border-color: {border} !important;
}}
button[data-testid="stBaseButton-secondary"] p {{ color: {text} !important; }}
[data-testid="stFileUploaderDropzone"] {{ background-color: {bg2} !important; }}
[data-testid="stFileUploaderDropzone"] :is(span, small, div) {{ color: {text} !important; }}
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {{
    background-color: {bg2} !important;
}}
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea,
[data-baseweb="select"] input, [data-baseweb="select"] > div div {{
    color: {text} !important;
}}
[data-baseweb="popover"] [data-baseweb="menu"], [data-baseweb="popover"] ul {{
    background-color: {bg2} !important;
}}
[data-baseweb="popover"] li, [data-baseweb="popover"] li div {{ color: {text} !important; }}
[data-testid="stExpander"] summary {{ color: {text} !important; }}
[data-testid="stExpander"] details {{ border-color: {border} !important; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-color: {border} !important; }}
[data-testid="stThumbValue"], [data-testid="stTickBarMin"], [data-testid="stTickBarMax"] {{
    color: {text} !important;
}}
</style>
"""


# ================================
# 1. 介面與基本設定
# ================================
st.set_page_config(page_title="Casino Game AI 競品分析儀", page_icon="🎰", layout="wide")

import streamlit.components.v1 as components

# 初始化主題狀態（第一次載入時跟隨目前實際主題，之後由切換按鈕控制）
if "ui_theme" not in st.session_state:
    st.session_state["ui_theme"] = detect_theme_base()
is_dark_theme = st.session_state["ui_theme"] == "dark"
hint_color = "#9ca3af" if is_dark_theme else "#6b7280"

# 注入 Google Fonts + 自定義 CSS
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap');
html, body, [class*="css"] {{
    font-family: 'Noto Sans TC', 'Microsoft JhengHei', sans-serif !important;
}}
h1 {{ letter-spacing: -0.02em; }}
.block-container {{ padding-top: 2rem; padding-bottom: 3rem; }}
[data-testid="stMetricValue"] {{ font-size: 1.35rem; }}
.section-hint {{ color: {hint_color}; font-size: 0.92rem; margin-top: -0.4rem; }}
/* 寬螢幕時讓右側「本次分析」面板黏在畫面上，捲動時開始分析按鈕不會消失 */
@media (min-width: 992px) {{
    [data-testid="stColumn"]:has(.st-key-summary_panel) {{
        position: sticky;
        top: 4.2rem;
        align-self: flex-start;
    }}
}}
</style>
""", unsafe_allow_html=True)

# 同一個 session 內曾切換主題時，注入即時覆蓋樣式（詳見 build_theme_override_css 說明）
if st.session_state.get("theme_live_override"):
    st.markdown(build_theme_override_css(st.session_state["ui_theme"]), unsafe_allow_html=True)

# 初始化 Session State
if "is_analyzing" not in st.session_state:
    st.session_state["is_analyzing"] = False
if "analysis_done" not in st.session_state:
    st.session_state["analysis_done"] = False
if "report_md" not in st.session_state:
    st.session_state["report_md"] = ""
if "styled_html" not in st.session_state:
    st.session_state["styled_html"] = ""
if "analysis_history" not in st.session_state:
    st.session_state["analysis_history"] = load_analysis_history()
if "access_granted" not in st.session_state:
    st.session_state["access_granted"] = False

server_api_key = get_secret_value("GEMINI_API_KEY")
app_password = get_secret_value("APP_PASSWORD")

title_col, theme_col = st.columns([5, 1], vertical_alignment="center")
with title_col:
    st.title("🎰 Casino Game AI 競品分析儀")
with theme_col:
    st.button(
        "☀️ 淺色模式" if is_dark_theme else "🌙 深色模式",
        on_click=toggle_theme,
        width="stretch",
        help="切換整個介面的深色 / 淺色主題。",
    )
if st.session_state.get("theme_native_sync_error"):
    st.warning(
        "原生主題設定暫時無法同步，目前已改用頁面樣式完成切換；"
        "重新整理後可能回到伺服器的預設主題。"
    )
st.caption("🏷️ 版本：v1.4.1 (介面與體驗優化)")
st.markdown("快速比較自家產品與市面競品的遊玩體驗差異，並產生具有體感的結構化改善報告。")

if app_password and not st.session_state["access_granted"]:
    with st.container(border=True):
        st.subheader("🔐 內部工具登入")
        entered_password = st.text_input("請輸入使用密碼", type="password")
        if st.button("進入工具", type="primary"):
            if entered_password == app_password:
                st.session_state["access_granted"] = True
                st.rerun()
            else:
                st.error("密碼不正確，請確認後再試。")
    st.stop()

# 側邊欄：設定
with st.sidebar:
    st.header("⚙️ 設定與權限")
    if server_api_key:
        st.success("已使用 Streamlit Secrets 中的 Gemini API Key。")
        api_key_input = server_api_key
    else:
        api_key_input = st.text_input("輸入個人 Gemini API Key", type="password")
        st.markdown("[🔑 點此前往 Google AI Studio 取得 API Key](https://aistudio.google.com/app/apikey)")
        st.info("目前使用個人 API Key 模式：每位使用者輸入自己的 Key，費用與額度會算在各自的 Google AI 帳號。")

    model_choice = st.selectbox(
        "Gemini 模型",
        MODEL_IDS,
        format_func=model_display_name,
        help=(
            "建議使用 Gemini 3.5 Flash（適合影片分析與結構化報告）。"
            "Preview 模型可能變動；Pro 模型偏重品質，但通常需要付費額度。"
        )
    )

    st.markdown("---")
    with st.expander("📋 使用步驟（點我展開）", expanded=False):
        st.markdown("""
1. 🔑 輸入自己的 Gemini API Key
2. 🎮 選擇遊戲類型
3. 📹 上傳自家與競品影片
4. ⏱️ (選填) 指定分析區間
5. 🎯 (選填) 填寫特別觀察重點
6. 🚀 點擊「開始深度分析」
7. 📊 查看報告與雷達圖
8. 💾 下載完整 HTML 報告（含圖表）
""")

    with st.expander("💡 計費與隱私須知", expanded=False):
        st.error("⚠️ **非常重要 (個人 API Key 模式)**：\n分析影片會消耗大量 Token，費用與額度會算在輸入的 API Key 所屬帳號。通常需要綁定付費資訊 (Pay as you go) 才能穩定執行。")
        st.markdown("分析完畢後，雲端影片檔案將會被自動刪除，保護機密並確保不會浪費資源。")

st.markdown("---")

# ================================
# 2. 檔案上傳與選項區
# ================================
workspace_col, summary_col = st.columns([2.25, 1], gap="large")

with workspace_col:
    st.subheader("1. 基本資料")
    st.markdown('<p class="section-hint">先標記這次分析屬於哪個專案，後續報告與歷史紀錄會用這些資訊命名。</p>', unsafe_allow_html=True)
    with st.container(border=True):
        meta_col1, meta_col2 = st.columns(2)
        project_name = meta_col1.text_input(
            "專案 / 遊戲名稱",
            placeholder="例如：埃及主題 Slot v2",
            help="會寫入報告與歷史記錄，方便日後回看。"
        )
        analyst_name = meta_col2.text_input(
            "分析人員 / 企劃",
            placeholder="例如：產品企劃 Amy",
            help="僅用於報告標記，不會上傳到其他地方保存。"
        )
        game_type = st.selectbox(
            "遊戲類型",
            ["Slot 老虎機", "捕魚機", "撲克/棋牌", "其他"],
            help="輔助 AI 聚焦對應的核心特效節奏。"
        )

    st.subheader("2. 上傳影片")
    st.markdown('<p class="section-hint">請上傳自家與競品的實機遊玩影片。建議先用 30 秒到 3 分鐘片段做比較。</p>', unsafe_allow_html=True)
    upload_col1, upload_col2 = st.columns(2)
    with upload_col1:
        with st.container(border=True):
            st.subheader("🏠 自家遊戲")
            home_video = st.file_uploader("上傳自家遊戲影片 (MP4 / MOV / AVI)", type=["mp4", "mov", "avi"], key="home_vid")
            st.caption("支援拖放 · 建議包含完整遊玩流程")
            if home_video:
                st.video(home_video)

    with upload_col2:
        with st.container(border=True):
            st.subheader("🔥 競品遊戲")
            comp_video = st.file_uploader("上傳競品遊戲影片 (MP4 / MOV / AVI)", type=["mp4", "mov", "avi"], key="comp_vid")
            st.caption("支援拖放 · 建議與自家影片包含相近事件")
            if comp_video:
                st.video(comp_video)

    st.subheader("3. 分析設定")
    st.markdown('<p class="section-hint">全部為選填。想要更聚焦的報告時，再展開設定分析模式、觀察重點與時間區間。</p>', unsafe_allow_html=True)
    with st.expander("進階分析設定", expanded=False):
        analysis_modes = st.multiselect(
            "本次分析模式",
            list(ANALYSIS_MODE_GUIDES.keys()),
            default=["爽感與節奏", "UI/UX 操作", "美術特效"],
            help="可複選，AI 會依照選擇的方向調整觀察重點與建議格式。"
        )

        custom_focus = st.text_area(
            "🎯 本次分析有什麼特別想關注的細節嗎？（選填）",
            help="例如：特別注意 Free Game 的過場速度、中大獎的音效層次、按鈕擺放位置等。"
        )

        st.markdown("#### ⏱️ 分析區間設定")
        enable_time_range = st.checkbox("啟用指定分析區間 (僅分析精彩片段以節省 Token)", value=False)
        time_range_prompt = ""
        if enable_time_range:
            st.caption("先用滑桿選整體觀察範圍；若有重點事件，可在下方標記多個片段。")
            video_range_max = st.number_input(
                "影片可選範圍上限（秒）",
                min_value=30,
                max_value=900,
                value=180,
                step=30,
                help="Streamlit 無法穩定讀取所有瀏覽器上傳影片的實際長度，因此這裡用秒數上限控制滑桿範圍。"
            )
            default_end = min(30, int(video_range_max))
            home_range = st.slider(
                "🏠 自家遊戲整體分析範圍",
                min_value=0,
                max_value=int(video_range_max),
                value=(0, default_end),
                step=1,
                format="%d 秒",
                key="home_time_range",
            )
            st.caption(f"自家遊戲：{format_seconds(home_range[0])} 到 {format_seconds(home_range[1])}")
            comp_range = st.slider(
                "🔥 競品遊戲整體分析範圍",
                min_value=0,
                max_value=int(video_range_max),
                value=(0, default_end),
                step=1,
                format="%d 秒",
                key="comp_time_range",
            )
            st.caption(f"競品遊戲：{format_seconds(comp_range[0])} 到 {format_seconds(comp_range[1])}")

            st.markdown("#### 🎬 重點片段標記")
            segment_count = st.number_input(
                "要標記幾個重點片段？",
                min_value=0,
                max_value=5,
                value=0,
                step=1,
                help="例如一般 Spin、中小獎、Big Win、Free Game、Bonus 轉場。"
            )
            segment_lines = []
            for idx in range(int(segment_count)):
                with st.container(border=True):
                    st.markdown(f"**片段 {idx + 1}**")
                    seg_col1, seg_col2 = st.columns([1, 2])
                    segment_type = seg_col1.selectbox(
                        "片段類型",
                        SEGMENT_TYPES,
                        key=f"segment_type_{idx}",
                    )
                    segment_note = seg_col2.text_input(
                        "備註（選填）",
                        placeholder="例如：第 2 次 Big Win、Free Game 進場",
                        key=f"segment_note_{idx}",
                    )
                    seg_home_range = st.slider(
                        "🏠 自家片段時間",
                        min_value=0,
                        max_value=int(video_range_max),
                        value=(0, default_end),
                        step=1,
                        format="%d 秒",
                        key=f"segment_home_{idx}",
                    )
                    seg_comp_range = st.slider(
                        "🔥 競品片段時間",
                        min_value=0,
                        max_value=int(video_range_max),
                        value=(0, default_end),
                        step=1,
                        format="%d 秒",
                        key=f"segment_comp_{idx}",
                    )
                    note_text = f"；備註：{segment_note.strip()}" if segment_note.strip() else ""
                    segment_lines.append(
                        f"- {segment_type}{note_text}：自家 {format_seconds(seg_home_range[0])}-{format_seconds(seg_home_range[1])}；"
                        f"競品 {format_seconds(seg_comp_range[0])}-{format_seconds(seg_comp_range[1])}"
                    )

            segment_prompt = "\n".join(segment_lines) if segment_lines else "- 未標記特定事件片段，請依整體分析範圍觀察。"
            time_range_prompt = (
                f"\n\n⏱️ **重要指令（時間區段分析）**：\n"
                f"- 對於【自家遊戲】，請優先針對影片中 **{format_seconds(home_range[0])} 到 {format_seconds(home_range[1])}** 的畫面進行分析。\n"
                f"- 對於【競品遊戲】，請優先針對影片中 **{format_seconds(comp_range[0])} 到 {format_seconds(comp_range[1])}** 的畫面進行分析。\n"
                f"- 若下方有重點片段標記，請在報告中引用這些片段作為佐證，並比較同類事件的節奏、特效、音效、UI 提示與玩家爽感。\n"
                f"\n重點片段標記：\n{segment_prompt}"
            )
        else:
            time_range_prompt = ""

with summary_col:
    st.subheader("本次分析")
    with st.container(border=True, key="summary_panel"):
        selected_modes_preview = analysis_modes if "analysis_modes" in locals() else ["爽感與節奏", "UI/UX 操作", "美術特效"]
        st.caption("分析摘要")
        st.write(f"**專案**：{project_name.strip() or '未命名'}")
        st.write(f"**遊戲類型**：{game_type}")
        st.write(f"**分析模式**：{', '.join(selected_modes_preview)}")
        st.write(f"**模型**：{model_display_name(model_choice)}")

        if home_video and comp_video:
            home_size_mb = home_video.size / (1024 * 1024)
            comp_size_mb = comp_video.size / (1024 * 1024)
            total_size_mb = home_size_mb + comp_size_mb
            estimated_seconds = estimate_analysis_seconds(total_size_mb)
            metric_col1, metric_col2 = st.columns(2)
            metric_col1.metric("合計大小", f"{total_size_mb:.1f} MB")
            metric_col2.metric("預估等待", f"{estimated_seconds // 60}分{estimated_seconds % 60}秒")

            if total_size_mb >= HIGH_RISK_TOTAL_MB:
                st.error("影片偏大，建議裁切或啟用片段分析。")
            elif total_size_mb >= RECOMMENDED_TOTAL_MB:
                st.warning("影片合計偏高，建議使用片段分析。")
            elif not enable_time_range:
                st.info("目前會讓 AI 觀看整段影片。")
            else:
                st.success("設定看起來適合執行。")
        else:
            st.info("請先上傳自家與競品影片。")

        missing_items = []
        if not api_key_input:
            missing_items.append("Gemini API Key")
        if not home_video or not comp_video:
            missing_items.append("自家與競品影片")
        st.button(
            "🚀 開始深度分析",
            on_click=trigger_analysis,
            disabled=st.session_state.get("is_analyzing", False) or bool(missing_items),
            width="stretch",
            type="primary",
        )
        if missing_items:
            st.caption("⛔ 尚未就緒：請先補齊 " + "、".join(missing_items) + "。")
        elif st.session_state.get("is_analyzing", False):
            st.caption("⏳ 分析進行中，請稍候…")

# ================================
# 3. 核心處理函式
# ================================
def render_radar_chart(report_text):
    """
    嘗試從報告 Markdown 內找出 JSON 評分區塊，畫出雷達圖。
    回傳 (fig, clean_report, scores_dict | None)
    """
    import plotly.graph_objects as go
    categories = ['節奏爽快感', '視覺特效', '音效層次', 'UI直覺度', '期待感營造']
    # 取最後一個 JSON 區塊（AI 通常把評分 JSON 放在報告最末端）
    all_matches = list(re.finditer(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', report_text))
    if not all_matches:
        return None, report_text, None
    last_match = all_matches[-1]
    json_str = last_match.group(1)
    json_block_full = last_match.group(0)
    try:
        data = json.loads(json_str)
        def extract_scores(sd):
            if isinstance(sd, dict):
                return [float(sd.get(c, 0)) for c in categories]
            elif isinstance(sd, list) and len(sd) >= 5:
                return [float(v) for v in sd[:5]]
            return [0.0] * 5
        home_scores = extract_scores(data.get("home"))
        comp_scores = extract_scores(data.get("comp"))
        home_loop = home_scores + [home_scores[0]]
        comp_loop = comp_scores + [comp_scores[0]]
        cat_loop  = categories  + [categories[0]]
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=home_loop, theta=cat_loop, fill='toself', name='自家遊戲',
            line_color='#3b82f6', fillcolor='rgba(59,130,246,0.3)',
            mode='lines+markers+text',
            text=[f"{v:.0f}" for v in home_scores] + [""],
            textposition='top center'
        ))
        fig.add_trace(go.Scatterpolar(
            r=comp_loop, theta=cat_loop, fill='toself', name='競品遊戲',
            line_color='#ef4444', fillcolor='rgba(239,68,68,0.3)',
            mode='lines+markers+text',
            text=[f"{v:.0f}" for v in comp_scores] + [""],
            textposition='top center'
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
            showlegend=True, title="🎯 競品體驗維度對比"
        )
        sections = re.split(r'(?m)^---\s*$', report_text)
        clean_sections = [s for s in sections if json_block_full not in s]
        clean = "\n\n---\n\n".join(clean_sections).strip()
        return fig, clean, {"home": home_scores, "comp": comp_scores}
    except Exception:
        return None, report_text, None

def upload_video_to_gemini(client: genai.Client, uploaded_file, file_label: str = "") -> types.File:
    """
    將 Streamlit 的上傳檔案暫存到硬碟後使用新版 File API 上傳至 Gemini，
    並設計阻擋等待機制直到影片由 PROCESSING 變成 ACTIVE 狀態。
    """
    with st.spinner(f"正在傳送 {file_label} 至 Google AI..."):
        ext = pathlib.Path(uploaded_file.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())  # 用 getvalue() 避免 stream 耗盡問題，支援重複分析
            tmp_file_path = tmp_file.name

        try:
            mime_map = {".mp4": "video/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo"}
            mime_type = mime_map.get(ext.lower(), "video/mp4")

            upload_bar = st.progress(0, text=f"📤 {file_label} 正在上傳至 Google AI 雲端...") 
            myfile = client.files.upload(
                file=tmp_file_path,
                config=types.UploadFileConfig(mime_type=mime_type)
            )
            upload_bar.progress(30, text=f"✅ {file_label} 上傳完成，等待雲端處理...")

            max_wait = 120   # 最多等 120 秒
            waited = 0

            # 持續輪詢，直到狀態不再是 PROCESSING
            while myfile.state.name == "PROCESSING" and waited < max_wait:
                percent = min(30 + int((waited / max_wait) * 65), 95)
                upload_bar.progress(percent, text=f"⚙️ {file_label} 雲端處理中（{waited}s），請稍候...")
                time.sleep(5)
                waited += 5
                myfile = client.files.get(name=myfile.name)

            upload_bar.progress(100, text=f"🎉 {file_label} 就緒！")
            time.sleep(0.4)
            upload_bar.empty()

            # 嚴格確認最終狀態必須為 ACTIVE
            if myfile.state.name != "ACTIVE":
                raise Exception(
                    f"{file_label} 處理失敗或逾時，最終狀態為：{myfile.state.name}（等待了 {waited}s）。"
                )

            st.toast(f"✅ {file_label} 上傳完成！", icon="🎉")
            return myfile

        finally:
            if os.path.exists(tmp_file_path):
                os.remove(tmp_file_path)



# ================================
# 4. 執行按鈕與報告渲染區
# ================================
if st.session_state.get("is_analyzing", False):
    if not api_key_input:
        st.error("請先於左側欄位輸入 Gemini API Key。")
        st.session_state["is_analyzing"] = False
        st.stop()

    if not home_video or not comp_video:
        st.error("請確保「自家遊戲」與「競品遊戲」皆已成功上傳影片。")
        st.session_state["is_analyzing"] = False
        st.stop()

    # 建立新版 Client
    client = genai.Client(api_key=api_key_input)
    file1, file2 = None, None

    try:
        # 上傳兩段影片
        file1 = upload_video_to_gemini(client, home_video, "自家遊戲影片")
        file2 = upload_video_to_gemini(client, comp_video, "競品遊戲影片")

        # 定義 Prompt 變數
        custom_focus_prompt = f"\n\n🚨 **使用者特別指定的觀察重點**：\n{custom_focus}\n請特別針對上述要求進行分析與解答。" if custom_focus.strip() else ""
        selected_mode_guides = analysis_modes or ["爽感與節奏", "UI/UX 操作", "美術特效"]
        mode_prompt = "\n".join(
            f"- {mode}: {ANALYSIS_MODE_GUIDES[mode]}"
            for mode in selected_mode_guides
            if mode in ANALYSIS_MODE_GUIDES
        )
        report_context_prompt = "\n".join([
            f"- 專案 / 遊戲名稱：{project_name.strip() or '未填寫'}",
            f"- 分析人員 / 企劃：{analyst_name.strip() or '未填寫'}",
            f"- 遊戲類型：{game_type}",
            f"- 分析模式：{', '.join(selected_mode_guides)}",
        ])
        
        prompt = f"""你是一位資深博弈遊戲測試員、UX 研究員與遊戲企劃顧問。請仔細觀看兩支【{game_type}】的實機遊玩影片，進行深度的競品差異分析，並產生一份可直接交給企劃、美術、前端與音效團隊使用的結構化報告。
第一支影片為【自家遊戲】，第二支影片為【競品遊戲】。{custom_focus_prompt}{time_range_prompt}

本次報告背景：
{report_context_prompt}

本次分析模式與側重：
{mode_prompt}

分析重點需包含：
1. 核心節奏與操作感：Spin/發牌的速度、連押的流暢度、以及中獎前的『期待感營造（例如老虎機的聽牌/Scatter 特效延遲）』。
2. 視覺與聽覺回饋：小獎、大獎（Big Win / Mega Win）的慶祝特效（如金幣噴發、全螢幕動畫）、音效的疊加層次，以及長時間觀看是否容易視覺疲勞。
3. UI/UX 佈局：押注金額調整的直覺性、Spin 按鈕配置、餘額與贏分顯示的清晰度。
4. 特殊玩法展演：Free Spin（免費遊戲）或 Bonus Game 的轉場流暢度與規則清晰度。
5. 落地改版價值：請把觀察結果翻成可排進下一版 Sprint 的任務、驗收標準與風險提醒。

請嚴格使用以下 Markdown 架構輸出報告（請善用粗體、列點與分隔線 `---` 讓排版極度容易閱讀，並加入適當的 Emoji 增添質感）：

## 🎯 1. 主管摘要
> (請用 3～5 句話精準總結兩款產品在玩家爽感、視覺/音效刺激、操作理解與改版優先順序上的最大差異。請避免空泛形容，必須提到至少 1 個具體影片觀察。)

---
## 🧭 2. 分析背景
- 專案 / 遊戲名稱：
- 分析人員 / 企劃：
- 遊戲類型：
- 分析模式：
- 影片觀察範圍：

---
## ⚖️ 3. 優劣勢對比

### 🌟 自家產品優勢：
- (具體優勢 1，附影片畫面或時間軸佐證)
- ... (共 3 點)

### ⚠️ 自家需改善劣勢：
- (具體劣勢 1，附影片畫面或時間軸佐證)
- ... (共 3 點)

### 🧱 建議保留的設計：
- (列出 2 點自家目前不應該輕易改掉的優勢或既有體驗)

---
## 🔍 4. 關鍵差異深度解析
(針對上述『分析重點』或『使用者特別指定的觀察重點』，給出具體的比較，必須明確指出影片中發生差異的『具體畫面』或『時間軸』作為佐證。)

---
## 🧩 5. 可執行改版建議
請用表格輸出 3～5 個建議，欄位必須包含：
| 優先級 | 問題 | 如何改 | 負責角色 | 預估成本 | 預期效果 | 驗收標準 |

優先級請使用 P0 / P1 / P2。負責角色可包含企劃、美術、前端、音效、測試。預估成本請用低 / 中 / 高。

---
## 🧪 6. 下一版驗收清單
- (列出 5～8 條可直接測試的驗收條件，例如「Big Win 觸發後 1.5 秒內必須出現全螢幕慶祝動畫」)

---
## 📝 7. 可直接建立的任務卡
請輸出 2～4 張任務卡，每張包含：
- 任務標題：
- 背景問題：
- 修改內容：
- 驗收條件：
- 風險提醒：

---
## 📊 8. 數據化評分
請為兩款產品在以下 5 個維度給出 1~10 分的體驗評分。每個分數都請先用一行文字解釋原因，最後再**嚴格將結果以 JSON 格式包裝在 ```json 與 ``` 區塊內**，放置於報告的最尾端。
維度包含：節奏爽快感、視覺特效、音效層次、UI直覺度、期待感營造。
格式範例：
```json
{{
  "home": {{"節奏爽快感": 8, "視覺特效": 7, "音效層次": 6, "UI直覺度": 8, "期待感營造": 7}},
  "comp": {{"節奏爽快感": 9, "視覺特效": 9, "音效層次": 8, "UI直覺度": 7, "期待感營造": 9}}
}}
```
"""

        st.markdown("### 📊 競品體驗分析報告")

        # 根據影片大小動態估算 AI 回應時間（秒）
        total_size_mb = (home_video.size + comp_video.size) / (1024 * 1024)
        estimated_seconds = estimate_analysis_seconds(total_size_mb)

        st.caption("⏱️ 以下為預估階段，實際時間依 Gemini 處理速度與影片長度而異。")
        _progress_html = build_estimated_progress_html(estimated_seconds, is_dark_theme)
        progress_placeholder = st.empty()
        with progress_placeholder:
            components.html(_progress_html, height=40)

        response_stream = client.models.generate_content_stream(
            model=model_choice,
            contents=[
                types.Part.from_uri(file_uri=file1.uri, mime_type=file1.mime_type),
                types.Part.from_uri(file_uri=file2.uri, mime_type=file2.mime_type),
                prompt,
            ]
        )
        
        def stream_parser():
            first = True
            for chunk in response_stream:
                if first:
                    progress_placeholder.empty() # 清除原本的動態 HTML 進度條
                    first = False
                if chunk.text:
                    yield chunk.text
        
        full_response_text = st.write_stream(stream_parser())
        st.toast("🎉 分析完成！", icon="🎉")
        
        # 將 Markdown 轉成精美的 HTML（含雷達圖）
        # 先解析雷達圖，以便把圖表嵌入 HTML
        _fig_export, _clean_export, _scores_export = render_radar_chart(full_response_text)
        radar_html_embed = _fig_export.to_html(full_html=False, include_plotlyjs='inline') if _fig_export else ""
        html_body = md_lib.markdown(_clean_export if _clean_export else full_response_text, extensions=['tables'])
        analyzed_at = datetime.now().strftime("%Y/%m/%d %H:%M")
        report_meta = {
            "time": analyzed_at,
            "project_name": project_name.strip() or "未命名專案",
            "analyst_name": analyst_name.strip() or "未填寫",
            "game_type": game_type,
            "analysis_modes": selected_mode_guides,
            "model": model_choice,
        }
        report_meta_html = "".join([
            f"<span><strong>專案</strong>{html_lib.escape(report_meta['project_name'])}</span>",
            f"<span><strong>分析人員</strong>{html_lib.escape(report_meta['analyst_name'])}</span>",
            f"<span><strong>遊戲類型</strong>{html_lib.escape(report_meta['game_type'])}</span>",
            f"<span><strong>分析模式</strong>{html_lib.escape(', '.join(report_meta['analysis_modes']))}</span>",
            f"<span><strong>時間</strong>{html_lib.escape(report_meta['time'])}</span>",
            f"<span><strong>模型</strong>{html_lib.escape(report_meta['model'])}</span>",
        ])

        styled_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>競品體驗分析報告</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Noto Sans TC','Microsoft JhengHei',sans-serif; line-height:1.8; color:#2d3748; background:#edf2f7; margin:0; padding:40px 20px; }}
        .container {{ max-width:850px; margin:0 auto; background:#fff; padding:40px 50px; border-radius:12px; box-shadow:0 10px 25px rgba(0,0,0,.05); }}
        .meta {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; margin:0 0 28px; padding:16px; background:#f7fafc; border:1px solid #e2e8f0; border-radius:8px; }}
        .meta span {{ font-size:14px; color:#4a5568; }}
        .meta strong {{ display:block; color:#2d3748; font-size:12px; letter-spacing:.04em; margin-bottom:2px; }}
        h2 {{ border-bottom:3px solid #ebf8ff; padding-bottom:.4em; color:#2b6cb0; margin-top:1.5em; }}
        blockquote {{ margin:1.5em 0; padding:1em 1.5em; background:#ebf8ff; border-left:5px solid #3182ce; border-radius:0 8px 8px 0; color:#2c5282; font-weight:500; }}
        ul,ol {{ padding-left:24px; margin-bottom:1.5em; }} li {{ margin-bottom:.5em; }}
        table {{ border-collapse:collapse; width:100%; margin:2em 0; border-radius:8px; overflow:hidden; box-shadow:0 4px 6px rgba(0,0,0,.05); }}
        th,td {{ padding:12px 15px; text-align:left; }} th {{ background:#4299e1; color:#fff; font-weight:600; }}
        tr:nth-child(even) {{ background:#f7fafc; }}
        hr {{ border:0; height:1px; background:#e2e8f0; margin:3em 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="meta">{report_meta_html}</div>
        {radar_html_embed}
        {html_body}
    </div>
</body>
</html>"""

        analysis_record = {
            **report_meta,
            "report_md": full_response_text,
            "styled_html": styled_html,
        }
        # 先完成持久化，再提交 session 成功狀態，避免寫檔失敗卻顯示為成功。
        persist_analysis_record(
            st.session_state,
            analysis_record,
            save_analysis_history,
            MAX_HISTORY_ITEMS,
        )
        # 存入 session_state 避免畫面重整消失
        st.session_state["report_md"] = full_response_text
        st.session_state["styled_html"] = styled_html
        st.session_state["analysis_done"] = True

    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "Quota exceeded" in error_msg:
            st.error("🚨 **API 額度已耗盡 (Quota Exceeded)**")
            st.warning("⚠️ **原因**：您目前使用的 API Key 處於「免費 Tier (Free Tier)」，而免費方案上傳分析兩部影片極易超過長內容的 Token 限制，或是您的地區剛好未開放免費額度。")
            st.info("👉 **建議處理**：改用較短片段、啟用分析區間，或請該 API Key 的持有人確認 Google AI Studio / Cloud 專案的帳單與額度。")
            with st.expander("詳細原始錯誤訊息"):
                st.write(error_msg)
        elif "API_KEY_INVALID" in error_msg or "invalid api key" in error_msg.lower() or "permission" in error_msg.lower():
            st.error("🔑 **API Key 無法使用**")
            st.info("請確認 Key 是否貼完整、是否屬於正確的 Google AI 專案，以及該專案是否允許使用 Gemini API。")
            with st.expander("詳細原始錯誤訊息"):
                st.write(error_msg)
        elif "處理失敗或逾時" in error_msg or "PROCESSING" in error_msg or "timeout" in error_msg.lower() or "deadline" in error_msg.lower():
            st.error("⏱️ **影片處理逾時或雲端尚未完成解析**")
            st.info("建議先裁切影片、降低解析度，或只用上方片段標記分析 Big Win / Free Game 等重點事件後再重試。")
            with st.expander("詳細原始錯誤訊息"):
                st.write(error_msg)
        elif "mime" in error_msg.lower() or "unsupported" in error_msg.lower() or "file" in error_msg.lower():
            st.error("📹 **影片檔案可能無法被 Gemini 正常讀取**")
            st.info("請確認影片是 MP4 / MOV / AVI，並盡量使用 H.264 編碼的 MP4。若仍失敗，先用剪輯工具重新輸出短片再上傳。")
            with st.expander("詳細原始錯誤訊息"):
                st.write(error_msg)
        else:
            st.error(f"分析過程中發生異常：{e}")
            st.info("如果這不是 API Key 或額度問題，建議先縮短影片、重新整理頁面後再試一次。")

    finally:
        # 清除雲端伺服器上的暫存影片，節省 Quota
        for f in [file1, file2]:
            if f:
                try:
                    client.files.delete(name=f.name)
                except Exception:
                    pass

        # 不論成功失敗，都要解除按鈕鎖定並重整畫面
        st.session_state["is_analyzing"] = False
        st.rerun()

# ================================
# 5. 結果渲染與狀態保留區
# ================================

if st.session_state.get("analysis_history"):
    st.markdown("---")
    history = st.session_state["analysis_history"]
    # 剛完成新分析時，自動跳到最新一筆報告，避免畫面停留在先前選取的舊報告
    if st.session_state.pop("just_analyzed", False):
        st.session_state["selected_history_idx"] = len(history) - 1
    if "selected_history_idx" not in st.session_state:
        st.session_state["selected_history_idx"] = len(history) - 1
    st.session_state["selected_history_idx"] = min(st.session_state["selected_history_idx"], len(history) - 1)
    current_report = history[st.session_state["selected_history_idx"]]

    st.markdown("## 📊 目前顯示的分析報告")
    st.caption(f"🗂️ 歷史紀錄 · 分析時間：{current_report.get('time') or '未記錄'}")
    meta_cols = st.columns(4)
    meta_cols[0].caption(f"專案：{current_report.get('project_name', '未命名專案')}")
    meta_cols[1].caption(f"分析人員：{current_report.get('analyst_name', '未填寫')}")
    meta_cols[2].caption(f"模式：{', '.join(current_report.get('analysis_modes', [])) or '未記錄'}")
    meta_cols[3].caption(
        f"模型：{model_display_name(current_report.get('model') or '未記錄')}"
    )

    fig, clean_report, scores = render_radar_chart(current_report["report_md"])
    safe_project = re.sub(r'[\\/:*?"<>|\s]+', '_', current_report.get('project_name', '競品分析')).strip('_')
    safe_time = current_report.get('time', '').replace('/', '-').replace(' ', '_').replace(':', '')
    report_html = current_report.get("styled_html", "")
    task_cards_text = extract_task_cards(current_report.get("report_md", ""))

    overview_tab, tasks_tab, report_tab, export_tab, history_tab = st.tabs(
        ["📊 總覽", "📝 任務卡", "📄 完整報告", "💾 下載", "🗂️ 歷史"]
    )

    with overview_tab:
        if scores:
            home_avg = sum(scores["home"]) / len(scores["home"])
            comp_avg = sum(scores["comp"]) / len(scores["comp"])
            gap = comp_avg - home_avg
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("🏠 自家平均分", f"{home_avg:.1f} / 10")
            mc2.metric("🔥 競品平均分", f"{comp_avg:.1f} / 10")
            mc3.metric("🎯 差距", f"{abs(gap):.1f} 分",
                       delta=f"自家落後 {abs(gap):.1f} 分" if gap > 0 else f"自家領先 {abs(gap):.1f} 分",
                       delta_color="inverse" if gap > 0 else "normal")
            categories = ['節奏爽快感', '視覺特效', '音效層次', 'UI直覺度', '期待感營造']
            score_gaps = [
                {
                    "維度": category,
                    "自家": scores["home"][idx],
                    "競品": scores["comp"][idx],
                    "差距": scores["comp"][idx] - scores["home"][idx],
                }
                for idx, category in enumerate(categories)
            ]
            score_gaps.sort(key=lambda item: abs(item["差距"]), reverse=True)
            with st.expander("🔎 分數差距最大的維度", expanded=True):
                for item in score_gaps[:3]:
                    if item["差距"] > 0:
                        st.write(
                            f"- **{item['維度']}**：自家 {item['自家']:.0f} / 競品 {item['競品']:.0f}，"
                            f"自家落後 {abs(item['差距']):.0f} 分。"
                        )
                    elif item["差距"] < 0:
                        st.write(
                            f"- **{item['維度']}**：自家 {item['自家']:.0f} / 競品 {item['競品']:.0f}，"
                            f"自家領先 {abs(item['差距']):.0f} 分。"
                        )
                    else:
                        st.write(f"- **{item['維度']}**：雙方同分，都是 {item['自家']:.0f} 分。")
            st.markdown("---")
        else:
            st.info("此報告沒有可解析的 JSON 評分，因此暫時無法顯示雷達圖與分數摘要。")

        if fig:
            st.plotly_chart(fig, width="stretch")

        with st.expander("查看完整 AI 報告內容", expanded=False):
            st.markdown(clean_report)

    with tasks_tab:
        st.markdown("### 📝 可直接建立的任務卡")
        st.markdown(task_cards_text)

    with report_tab:
        st.markdown(clean_report)

    with export_tab:
        st.markdown("您可以下載完整報告、Word 相容檔、Markdown 備份，或只下載任務卡給 Jira / Trello / Notion 使用。")
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 下載 HTML 報告 (推薦，保留排版)",
                data=report_html,
                file_name=f"{safe_project or '競品分析報告'}_{safe_time}.html",
                mime="text/html",
                type="primary",
                width="stretch"
            )
        with col2:
            st.download_button(
                label="📝 下載 Markdown 報告 (原始備份)",
                data=current_report["report_md"],
                file_name=f"{safe_project or '競品分析報告'}_{safe_time}.md",
                mime="text/markdown",
                width="stretch"
            )
        col3, col4 = st.columns(2)
        with col3:
            st.download_button(
                label="📄 下載 Word 相容報告 (.doc)",
                data=report_html.encode("utf-8"),
                file_name=f"{safe_project or '競品分析報告'}_{safe_time}.doc",
                mime="application/msword",
                width="stretch"
            )
        with col4:
            st.download_button(
                label="🧾 下載任務卡文字",
                data=task_cards_text,
                file_name=f"{safe_project or '競品分析任務卡'}_{safe_time}.txt",
                mime="text/plain",
                width="stretch"
            )

    with history_tab:
        st.markdown("### 🗂️ 歷史資料管理")
        if len(history) > 1:
            history_labels = [
                f"第 {i+1} 次｜{h.get('project_name', '未命名專案')}｜{h.get('game_type', '未分類')}｜{h.get('time', '')}"
                for i, h in enumerate(history)
            ]
            st.selectbox(
                f"歷史報告記錄（共 {len(history)} 筆，可切換查看）",
                range(len(history_labels)),
                format_func=lambda i: history_labels[i],
                key="selected_history_idx",
            )
            st.info("切換歷史報告後，上方總覽、任務卡、完整報告與下載分頁會同步顯示選取的報告。")
        else:
            st.info("目前只有 1 筆歷史報告。")

        history_json = json.dumps(st.session_state["analysis_history"], ensure_ascii=False, indent=2)
        hcol1, hcol2 = st.columns(2)
        with hcol1:
            st.download_button(
                label="📦 備份全部歷史紀錄 (JSON)",
                data=history_json,
                file_name=f"analysis_history_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json",
                width="stretch"
            )
        with hcol2:
            confirm_clear = st.checkbox("我確認要清空本機歷史紀錄", key="confirm_clear_history")
            if st.button("🗑️ 清空本機歷史", disabled=not confirm_clear, width="stretch"):
                st.session_state["analysis_history"] = []
                save_analysis_history([])
                st.success("本機歷史紀錄已清空。")
                st.rerun()

    st.caption(f"💡 小提示：歷史報告會保存在本機 `{HISTORY_FILE}`，重新開啟工具後仍可回看最近 {MAX_HISTORY_ITEMS} 筆。")
elif not st.session_state.get("is_analyzing", False):
    st.markdown("---")
    with st.container(border=True):
        st.markdown("#### 📄 分析報告會顯示在這裡")
        st.markdown("上傳自家與競品影片、點擊「🚀 開始深度分析」後，完整報告、雷達圖、任務卡與下載選項都會出現在此區。")
