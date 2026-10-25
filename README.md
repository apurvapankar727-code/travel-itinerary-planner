# 🧭 Personalized Travel Itinerary Planner
Skill Wallet Capstone Project 4 — built with Python, Streamlit and SQLite.

## Features
- **Destination Recommender:** top 3 matches by vibe, budget, season and interests.
- **Day-Wise Itinerary:** Morning / Lunch / Afternoon / Evening slots, one area per day, running cost tracker in INR and USD.
- **Customize Activities:** swap a single slot ("vegetarian lunch", "outdoor market") or regenerate one day without touching the rest.
- **Trips & PDF Export:** save trips to SQLite, reload or delete them, and download a PDF guide with an emergency checklist.
- **Demo mode:** works with no API key. Goa, Jaipur and Manali are detailed; other cities use a generic template.
- **AI mode:** paste a Google Gemini API key in the sidebar for any destination. Responses are requested as JSON and validated; on failure the app falls back to demo mode.

## Run locally
```
pip install -r requirements.txt
streamlit run app.py
```

## Deploy (Streamlit Community Cloud)
Push this repo to GitHub, open share.streamlit.io, choose the repo and set the main file to `app.py`.

## Important notes
- **Optimization is area-based:** activities are grouped by area per day to reduce transit. Distances are straight-line estimates, not verified shortest routes (no live routing API).
- **Costs are estimates:** activities, accommodation and local transport use fixed assumptions by budget level. The INR/USD rate is user-editable.
- **Storage:** trips are saved in a local `trips.db`. On Streamlit Cloud this file can reset on restart or redeploy.
- **Model name:** the Gemini model is editable in the sidebar (default `gemini-3.8-flash`) because Google retires models regularly.
- Never commit your API key. Enter it in the sidebar at runtime.

## Tech stack
Python 3.9+, Streamlit, SQLite, pandas, ReportLab, Google Gemini API (optional).
