import logging
import os
import random
import subprocess
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from bs4 import BeautifulSoup

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
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
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
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
]


def _curl(url: str) -> str:
    ua = random.choice(USER_AGENTS)
    result = subprocess.run(
        ["curl", "-s", "-H", f"User-Agent: {ua}", "--max-time", "15", url],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")
    return result.stdout


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/top-posts")
def top_posts(limit: int = 10):
    html = _curl("https://old.reddit.com/r/all/top/?t=day")
    soup = BeautifulSoup(html, "html.parser")
    things = soup.find_all("div", class_="thing", id=lambda x: x and x.startswith("thing_t3_"))
    posts = []
    for thing in things[:limit]:
        title_el = thing.find("a", class_="title")
        title = title_el.get_text(strip=True) if title_el else "Untitled"
        permalink = thing.get("data-permalink", "")
        url = f"https://www.reddit.com{permalink}" if permalink else ""
        score = int(thing.get("data-score", 0))
        comments = int(thing.get("data-comments-count", 0))
        domain_el = thing.find("span", class_="domain")
        subreddit = ""
        if domain_el:
            sub_text = domain_el.get_text(strip=True)
            if sub_text.startswith("(") and sub_text.endswith(")"):
                subreddit = sub_text[1:-1]
        posts.append({
            "url": url,
            "title": title,
            "score": score,
            "comments": comments,
            "subreddit": subreddit,
        })
    return posts


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
