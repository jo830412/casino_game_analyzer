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

## Deploy on Streamlit Community Cloud

1. Open Streamlit Community Cloud: <https://share.streamlit.io/>
2. Create a new app from this GitHub repository:
   - Repository: `jo830412/casino_game_analyzer`
   - Branch: `main`
   - Main file path: `app.py`
3. Open **Advanced settings**.
4. Optional: In **Secrets**, add an internal access password:

```toml
APP_PASSWORD = "optional-internal-password"
```

`APP_PASSWORD` is optional. If it is set, users must enter the password before using the app.

The current deployment is intended for personal API Key usage. Do not set `GEMINI_API_KEY` unless the company later prepares an official shared key. When `GEMINI_API_KEY` is not set, each user enters their own Gemini API Key in the sidebar, and usage is billed to that user's Google AI account.

5. Deploy the app and share the generated Streamlit URL with your team.

## Notes

- Current mode: each user enters their own Gemini API Key.
- Future company mode: set `GEMINI_API_KEY` in Streamlit Secrets so users do not need to enter their own API Key.
- Do not commit `.env`, `.streamlit/secrets.toml`, `.venv/`, `__pycache__/`, or `data/`.
- Video analysis may consume significant tokens. Prefer shorter clips or marked segments for repeated testing.
