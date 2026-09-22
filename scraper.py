import logging
import random
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

ATOM_NS = "http://www.w3.org/2005/Atom"
_BLOCK_TAGS = {"p", "div", "li", "blockquote", "pre", "table", "tr",
               "h1", "h2", "h3", "h4", "h5", "h6"}


def _q(tag: str) -> str:
    return f"{{{ATOM_NS}}}{tag}"


def _content_to_text(html: str) -> str:
    """Convert an Atom <content> HTML body to plain text.

    Prefers the `div.md` element (real post/comment body); falls back to the
    full content text. For link posts the content is a thumbnail table with no
    selftext — boilerplate is stripped and the result is an empty string.
    """
    if not html.strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    md = soup.find("div", class_="md")
    node = md if md is not None else soup
    for br in node.find_all("br"):
        br.replace_with("\n")
    for block in node.find_all(sorted(_BLOCK_TAGS)):
        block.append("\n")
    text = re.sub(r"[ \t]+", " ", node.get_text(" "))
    text = re.sub(r" *\n *", "\n", text).strip()
    if md is None:
        text = _strip_boilerplate(text)
    return text


def _strip_boilerplate(text: str) -> str:
    """Remove the "[link] [comments] submitted by /u/… to r/…" wrapper that
    Reddit uses for link-post bodies; an empty remainder means no selftext."""
    text = re.sub(r"\[(link|comments|removed|deleted)\]", " ", text)
    text = re.sub(r"submitted\s+by", " ", text)
    text = re.sub(r"/u/\S+", " ", text)
    text = re.sub(r"r/\S+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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
    BASE = "https://www.reddit.com"

    def __init__(self, delay=2.0, max_retries=3):
        self.delay = delay
        self.max_retries = max_retries

    def _respect_rate_limit(self):
        time.sleep(self.delay + random.uniform(0.5, 1.5))

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/atom+xml,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    def _fetch(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(max(1, self.max_retries)):
            self._respect_rate_limit()
            req = urllib.request.Request(url, headers=self._headers())
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                if e.code in (403, 404, 429):
                    log.warning("HTTP %d fetching %s", e.code, url)
                    reason = {403: "blocked", 404: "post not found or removed", 429: "rate limited"}
                    raise RuntimeError(f"Reddit RSS returned {e.code} — {reason[e.code]}") from e
                last_error = e
                log.warning("HTTP %d fetching %s (attempt %d/%d)", e.code, url, attempt + 1, self.max_retries)
            except (urllib.error.URLError, OSError) as e:
                last_error = e
                log.warning("Network error fetching %s: %s (attempt %d/%d)", url, e, attempt + 1, self.max_retries)
        raise RuntimeError(
            f"Reddit RSS unreachable after {self.max_retries} attempts: {last_error}"
        ) from last_error

    def fetch_post(self, url: str) -> RedditPost:
        xml = self._fetch(self._post_feed_url(url))
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            raise RuntimeError(f"Reddit RSS was not valid XML: {e}") from e

        post_entry = None
        comment_entries: list[ET.Element] = []
        for entry in root.findall(_q("entry")):
            entry_id = (entry.findtext(_q("id")) or "").strip()
            if entry_id.startswith("t3_"):
                post_entry = entry
            elif entry_id.startswith("t1_"):
                comment_entries.append(entry)

        if post_entry is None:
            raise RuntimeError("Reddit RSS contained no post entry — post may be removed")

        title = (post_entry.findtext(_q("title")) or "").strip()
        author = self._entry_author(post_entry)
        text = _content_to_text(self._entry_content(post_entry))
        link = self._entry_link(post_entry)
        comments = [
            {"author": self._entry_author(entry), "score": 0,
             "text": _content_to_text(self._entry_content(entry))}
            for entry in comment_entries
        ]
        comments = [c for c in comments if c["text"]]
        return RedditPost(url=link or url, title=title, author=author, score=0, text=text, comments=comments)

    def fetch_listing(self, limit: int = 10) -> list[dict]:
        xml = self._fetch(f"{self.BASE}/r/all/top/.rss?t=day")
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            raise RuntimeError(f"Reddit RSS was not valid XML: {e}") from e

        posts: list[dict] = []
        for entry in root.findall(_q("entry")):
            if len(posts) >= limit:
                break
            if not (entry.findtext(_q("id")) or "").startswith("t3_"):
                continue
            posts.append({
                "url": self._entry_link(entry),
                "title": (entry.findtext(_q("title")) or "").strip() or "Untitled",
                "score": 0,
                "comments": 0,
                "subreddit": self._entry_subreddit(entry),
            })
        if not posts:
            raise RuntimeError("No posts found in Reddit RSS listing")
        return posts

    def _post_feed_url(self, url: str) -> str:
        path = urlparse(url).path.rstrip("/")
        if not path.startswith("/r/"):
            raise ValueError(f"Not a valid Reddit post URL: {url}")
        if path.endswith(".rss"):
            return f"{self.BASE}{path}"
        return f"{self.BASE}{path}.rss"

    @staticmethod
    def _entry_author(entry: ET.Element) -> str:
        name_el = entry.find(f"{_q('author')}/{_q('name')}")
        name = (name_el.text or "").strip() if name_el is not None else ""
        if name.startswith("/u/"):
            name = name[3:]
        if not name or name in ("[deleted]", "[removed]"):
            return "unknown"
        return name

    @staticmethod
    def _entry_content(entry: ET.Element) -> str:
        content = entry.find(_q("content"))
        return "".join(content.itertext()) if content is not None else ""

    @staticmethod
    def _entry_link(entry: ET.Element) -> str:
        for link in entry.findall(_q("link")):
            href = link.get("href")
            if href:
                return href
        return ""

    @staticmethod
    def _entry_subreddit(entry: ET.Element) -> str:
        category = entry.find(_q("category"))
        if category is None:
            return ""
        return (category.get("term") or "").strip()
