def build_estimated_progress_html(total_seconds, is_dark_theme):
    total_seconds = max(1, int(total_seconds))
    if is_dark_theme:
        bar_track, bar_border, bar_fill = "#262730", "#444", "#FFC107"
        bar_text, bar_shadow = "#FAFAFA", "1px 1px 2px rgba(0,0,0,0.8)"
    else:
        bar_track, bar_border, bar_fill = "#F0F2F6", "#D1D5DB", "#D97706"
        bar_text, bar_shadow = "#31333F", "none"

    return (
        '<!DOCTYPE html><html><body style="margin: 0; padding: 0; font-family: sans-serif; overflow: hidden; background-color: transparent;">'
        f'<div style="width: 100%; height: 35px; background-color: {bar_track}; border-radius: 6px; position: relative; border: 1px solid {bar_border};">'
        f'<div id="ai-progress-bar" style="width: 0%; height: 100%; background-color: {bar_fill}; border-radius: 6px; transition: width 1s linear;"></div>'
        f'<div id="ai-progress-text" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: bold; color: {bar_text}; text-shadow: {bar_shadow};">👻 正在準備解析影片…（預估階段）</div>'
        '</div>'
        '<script>'
        'let pb = document.getElementById("ai-progress-bar");'
        'let pt = document.getElementById("ai-progress-text");'
        f'let t = 0; let total = {total_seconds};'
        'setInterval(() => {'
        '  t++;'
        '  let pct = Math.min((t/total)*95, 95);'
        '  if(pb) pb.style.width = pct + "%";'
        '  if(pt) {'
        '    if (t < 10) pt.innerText = "👀 正在解析影片（預估階段 · 已等待 " + t + " 秒）";'
        '    else if (t < 25) pt.innerText = "🧠 正在對比遊戲體驗（預估階段 · 已等待 " + t + " 秒）";'
        '    else if (t < 40) pt.innerText = "📝 正在整理分析報告（預估階段 · 已等待 " + t + " 秒）";'
        '    else if (t < total) pt.innerText = "✨ 正在完成報告（預估階段 · 已等待 " + t + " 秒）";'
        '    else pt.innerText = "⏳ Gemini 仍在處理，請繼續等待（已等待 " + t + " 秒）";'
        '  }'
        '}, 1000);'
        '</script>'
        '</body></html>'
    )
