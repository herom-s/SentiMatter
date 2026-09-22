# SentiMatter

Scrape any Reddit post and get a full 28-emotion sentiment breakdown of its title, body, and comments — no Reddit API key required.

Powered by **GoEmotions** (27 emotions + neutral) — int8-quantized [`roberta-base-go_emotions`](https://huggingface.co/SamLowe/roberta-base-go_emotions-onnx) running on ONNX Runtime.

## Stack

| Layer | Tech | Deploy |
|-------|------|--------|
| CLI | Python (argparse) | — |
| API | FastAPI + uvicorn | Railway |
| Frontend | React + Vite | Vercel |
| ML | ONNX Runtime (int8-quantized GoEmotions) | — |

## Quickstart

### Backend

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload
```

The model is preloaded at startup: the first run downloads ~120 MB from HuggingFace, later runs load from cache in a few seconds. With `--reload`, every code change restarts the server and reloads the model.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` when the API isn't running on `http://localhost:8000`.

### CLI (no server needed)

```bash
python main.py "https://www.reddit.com/r/..." --delay 2.0
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/health` | GET | Health check |
| `/top-posts?limit=10` | GET | Today's top posts from r/all (RSS, cached for 1 hour) |
| `/analyze` | POST | Analyze a post: `{"url": "https://www.reddit.com/r/.../comments/..."}` |

```bash
curl 'http://localhost:8000/top-posts?limit=5'

curl -X POST http://localhost:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://www.reddit.com/r/MadeMeSmile/comments/1uaj6fc/"}'
```

`/analyze` responds with the scraped post plus scores for all 28 emotions in four sections — `title`, `body`, `comments_avg`, and a 20/30/50-weighted `aggregated` — and the `dominant_emotion`.

## Deploy

### Backend → Railway

Connect the repo in Railway; the build is auto-detected from `requirements.txt` + `railway.toml`.

Optional — Reddit OAuth (recommended): create a free "script" app at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) and set:

| Variable | Value |
|----------|-------|
| `REDDIT_CLIENT_ID` | app client ID |
| `REDDIT_CLIENT_SECRET` | app secret |

With OAuth configured the API uses Reddit's official endpoints (real upvote scores, far higher rate limits) and automatically falls back to RSS if unset or failing.

### Frontend → Vercel

Set the root directory to `frontend/`, then configure:

| Variable | Value |
|----------|-------|
| `VITE_API_URL` | `https://your-backend.railway.app` |

## Architecture

1. **`scraper.py`** — fetches Reddit's public RSS/Atom feeds (`https://www.reddit.com{path}/.rss`) with `urllib`, parses them with `xml.etree`, and converts body/comment HTML to text with BeautifulSoup.
2. **`sentiment.py`** — runs the int8-quantized GoEmotions model on ONNX Runtime over the title, body, and a random sample of up to 80 comments; returns all 28 emotion scores per section plus a weighted aggregate.
3. **`server.py`** — FastAPI app that preloads the model at startup and exposes the REST endpoints.
4. **`frontend/`** — React SPA with emotion bar charts, summary cards, and live top-post examples.

## Notes & limitations

- **No scores without OAuth**: Reddit's RSS feeds don't expose upvotes, so `score` is 0 for posts and comments unless `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` are configured.
- **Rate limits**: without OAuth, Reddit rate-limits RSS per IP; `/top-posts` caches for 1 hour and falls back to a static list when the fetch fails.
- **Sampling**: comments are analyzed from a random sample of at most 80 (see `COMMENT_LIMIT` in `sentiment.py`).
- **Memory**: the quantized ONNX model keeps the API around ~350 MB, so it fits Railway's free tier (512 MB).
- Reddit's JSON API returns 403 and `old.reddit.com` redirects logged-out clients to a login wall, so RSS is the only keyless route.

## Requirements

- Python 3.12+ (see `.python-version`)
- Node 18+ for the frontend
- Internet connection (HuggingFace model download on first run)

## License

MIT — see [LICENSE](LICENSE).
