# SentiMatter

Scrape any Reddit post and run a 28-emotion sentiment analysis — no official API required.

Uses **GoEmotions** (27 emotions + neutral) via `SamLowe/roberta-base-go_emotions`.

## Stack

| Layer | Tech | Deploy |
|-------|------|--------|
| CLI | Python (argparse) | — |
| API | FastAPI + uvicorn | Railway |
| Frontend | React + Vite | Vercel |
| ML | HuggingFace Transformers + PyTorch | — |

## Local dev

```bash
# Backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

### CLI usage (no server needed)

```bash
python main.py "https://www.reddit.com/r/..." --delay 2.0
```

### API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/health` | GET | Health check |
| `/top-posts?limit=10` | GET | Scrapes today's top Reddit posts |
| `/analyze` | POST | Analyze a post: `{"url": "..."}` |

## Deploy

### Backend → Railway

Push to GitHub, connect repo in Railway. Auto-detected via `requirements.txt` + `railway.toml`.

Set env vars:

| Variable | Value |
|----------|-------|
| `CORS_ORIGINS` | `https://your-frontend.vercel.app` |

### Frontend → Vercel

Set root directory to `frontend/` in Vercel project settings.

Set env var:

| Variable | Value |
|----------|-------|
| `VITE_API_URL` | `https://your-backend.railway.app` |

## Architecture

1. **`scraper.py`** — fetches `old.reddit.com` HTML via `urllib`, parses with BeautifulSoup. Extracts title, author, score, body, comments.
2. **`sentiment.py`** — runs the HuggingFace model. Batches comments (up to 80, random sample) for speed. Returns scores across all 28 emotions per section (title / body / comments / weighted aggregate).
3. **`server.py`** — FastAPI server wrapping scraper + sentiment into REST endpoints.
4. **`frontend/`** — React SPA with emotion bar charts, summary cards, and live top-post examples.

## Requirements

- Python 3.10+
- Internet connection (model downloads ~500 MB on first run)
