import json
import logging
import os
import random
import time
import urllib.request

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from scraper import RedditScraper
from sentiment import SentimentAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("server")

app = FastAPI(title="SentiMatter API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

analyzer = None


def get_analyzer():
    global analyzer
    if analyzer is None:
        analyzer = SentimentAnalyzer()
    return analyzer


class AnalyzeRequest(BaseModel):
    url: str
    delay: float = 2.0


class AnalyzeResponse(BaseModel):
    post: dict
    sentiment: dict
    elapsed: float


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


def _fetch(url: str) -> str:
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        log.warning("HTTP %d fetching %s", e.code, url)
        raise RuntimeError(f"Reddit returned {e.code} — try again later")


@app.get("/")
def root():
    return {"name": "SentiMatter API", "version": "1.0.0", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/top-posts")
def top_posts(limit: int = 10):
    try:
        raw = _fetch("https://www.reddit.com/r/all/top/.json?t=day")
        data = json.loads(raw)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Invalid response from Reddit")

    posts = []
    for child in data.get("data", {}).get("children", [])[:limit]:
        d = child.get("data", {})
        permalink = d.get("permalink", "")
        posts.append({
            "url": f"https://www.reddit.com{permalink}" if permalink else "",
            "title": d.get("title", "Untitled"),
            "score": d.get("score", 0),
            "comments": d.get("num_comments", 0),
            "subreddit": d.get("subreddit", ""),
        })
    return posts


@app.get("/analyze")
def analyze_get():
    return {"message": "Send a POST request with {\"url\": \"...\"}"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    start = time.time()
    try:
        scraper = RedditScraper(delay=req.delay)
        post = scraper.fetch_post(req.url)
    except Exception as e:
        log.error("Failed to fetch post: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    try:
        sentiment = get_analyzer().analyze_post(post.title, post.text, post.comments)
    except Exception as e:
        log.error("Failed to analyze sentiment: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return AnalyzeResponse(
        post={
            "url": post.url,
            "title": post.title,
            "author": post.author,
            "score": post.score,
            "text": post.text,
            "comments": post.comments,
        },
        sentiment=sentiment,
        elapsed=round(time.time() - start, 2),
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
