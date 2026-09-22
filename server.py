import logging
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from scraper import RedditScraper
from sentiment import SentimentAnalyzer

log = logging.getLogger("server")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
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


@app.get("/")
def root():
    return {"name": "SentiMatter API", "version": "1.0.0", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


FALLBACK_POSTS = [
    {"url":"https://www.reddit.com/r/MadeMeSmile/comments/1uaj6fc/couple_sends_new_baby_text_to_wrong_number_dudes/","title":"Couple sends new baby text to wrong number, dudes show up anyway","score":71779,"comments":414,"subreddit":"MadeMeSmile"},
    {"url":"https://www.reddit.com/r/todayilearned/comments/1uai7pn/til_that_many_major_cities_have_disabled/","title":"TIL that many major cities have disabled thousands of crosswalk buttons","score":15434,"comments":382,"subreddit":"todayilearned"},
    {"url":"https://www.reddit.com/r/AskReddit/comments/1uas6k5/what_job_is_heavily_romanticized_in_movies_but/","title":"What job is heavily romanticized in movies but miserable in real life?","score":3104,"comments":1944,"subreddit":"AskReddit"},
    {"url":"https://www.reddit.com/r/gaming/comments/1uatrwg/ubisoft_cofounder_dies_in_tragic_plane_crash/","title":"Ubisoft co-founder dies in tragic plane crash","score":12148,"comments":859,"subreddit":"gaming"},
]

top_posts_cache = {"posts": None, "ts": 0.0}
CACHE_TTL = 3600


@app.get("/top-posts")
def top_posts(limit: int = 10):
    now = time.time()
    if top_posts_cache["posts"] and now - top_posts_cache["ts"] < CACHE_TTL:
        return top_posts_cache["posts"][:limit]

    try:
        posts = RedditScraper(delay=0).fetch_listing(limit=limit)
    except Exception as e:
        log.warning("Reddit fetch failed: %s — serving fallback", e)
        return FALLBACK_POSTS[:limit]
    top_posts_cache["posts"] = posts
    top_posts_cache["ts"] = now
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
