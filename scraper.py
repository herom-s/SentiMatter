import re
import time
import logging
import subprocess
import random
from urllib.parse import urlparse

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
]


def _parse_score(raw: str) -> int:
    raw = raw.replace(",", "").replace("points", "").replace("point", "").strip()
    multiplier = 1
    if raw.endswith(("k", "K")):
        multiplier = 1_000
        raw = raw[:-1]
    elif raw.endswith(("m", "M")):
        multiplier = 1_000_000
        raw = raw[:-1]
    try:
        return int(float(raw) * multiplier)
    except ValueError:
        return 0


class RedditPost:
    def __init__(self, url, title, author, score, text, comments):
        self.url = url
        self.title = title
        self.author = author
        self.score = score
        self.text = text
        self.comments = comments

    def __repr__(self):
        return (
            f"RedditPost(title={self.title!r}, author={self.author!r}, "
            f"score={self.score}, comments={len(self.comments)})"
        )


class RedditScraper:
    BASE = "https://old.reddit.com"

    def __init__(self, delay=2.0, max_retries=3):
        self.delay = delay
        self.max_retries = max_retries

    def _respect_rate_limit(self):
        time.sleep(self.delay + random.uniform(0.5, 1.5))

    def _fetch(self, url):
        self._respect_rate_limit()
        ua = random.choice(USER_AGENTS)
        result = subprocess.run(
            [
                "curl", "-s",
                "-H", f"User-Agent: {ua}",
                "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "-H", "Accept-Language: en-US,en;q=0.9",
                "--max-time", "30",
                url,
            ],
            capture_output=True, text=True, timeout=35,
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl failed: {result.stderr}")
        return result.stdout

    def fetch_post(self, url: str) -> RedditPost:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        if not path.startswith("/r/"):
            raise ValueError(f"Not a valid Reddit post URL: {url}")

        html = None
        for attempt in range(self.max_retries):
            try:
                html = self._fetch(f"{self.BASE}{path}/")
                if "Please wait for verification" in html:
                    raise RuntimeError("Blocked by JS challenge")
                break
            except Exception:
                if attempt < self.max_retries - 1:
                    wait = (attempt + 1) * 5
                    log.warning("Retrying in %ds…", wait)
                    time.sleep(wait)
                else:
                    raise

        soup = BeautifulSoup(html, "html.parser")

        thing = soup.find("div", class_="thing", id=lambda x: x and x.startswith("thing_t3_"))
        if not thing:
            raise RuntimeError("Could not find post data on page")

        title_el = thing.find("a", class_="title")
        title = title_el.get_text(strip=True) if title_el else ""

        author_el = thing.find("a", class_="author")
        author = author_el.get_text(strip=True) if author_el else "unknown"

        score = int(thing.get("data-score", 0)) if thing.get("data-score") else 0
        if score == 0:
            score_el = thing.find("span", class_="score")
            if score_el:
                score = _parse_score(score_el.get_text(strip=True))

        text = ""
        expando = thing.find("div", class_="expando")
        if expando:
            md = expando.find("div", class_="md")
            if md:
                for br in md.find_all("br"):
                    br.replace_with("\n")
                text = md.get_text(strip=True)

        comments = self._extract_comments(soup)

        return RedditPost(url=url, title=title, author=author, score=score, text=text, comments=comments)

    def _extract_comments(self, soup):
        comments = []
        for entry in soup.find_all("div", class_="entry"):
            if entry.find_parent("div", class_="link"):
                continue
            md = entry.find("div", class_="md")
            if not md:
                continue
            for br in md.find_all("br"):
                br.replace_with("\n")
            text = md.get_text(strip=True)
            if not text:
                continue

            author_el = entry.find("a", class_="author")
            author = author_el.get_text(strip=True) if author_el else "unknown"

            score_el = entry.find("span", class_="score")
            score = _parse_score(score_el.get_text(strip=True)) if score_el else 0

            comments.append({"author": author, "score": score, "text": text})
        return comments
