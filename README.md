# Casino Game AI Competitive Analyzer

Streamlit tool for comparing an in-house casino game video with a competitor video using Gemini video analysis. It produces a structured planning report, radar chart scores, improvement tasks, acceptance criteria, and exportable report files.

## Features

- Upload in-house and competitor gameplay videos (`mp4`, `mov`, `avi`)
- Select game type and analysis modes
- Mark analysis ranges and key segments such as Big Win, Free Game, and Bonus transitions
- Generate structured reports with priorities, owner roles, estimated cost, task cards, and acceptance criteria
- Render radar chart comparison from AI-generated scores
- Export HTML, Markdown, Word-compatible `.doc`, task card text, and history backup JSON
- Keep local analysis history under `data/analysis_history.json`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Or double-click `run_app.bat`.

## Notes

- The current version asks the user to enter a Gemini API Key in the sidebar.
- Do not commit `.env`, `.streamlit/secrets.toml`, `.venv/`, `__pycache__/`, or `data/`.
- Video analysis may consume significant tokens. Prefer shorter clips or marked segments for repeated testing.
