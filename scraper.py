import base64
import json
import logging
import os
import random
import re
import threading
import time
import urllib.error
import urllib.parse
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

OAUTH_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_API_BASE = "https://oauth.reddit.com"
DEFAULT_USER_AGENT = "python:sentimatter:1.0"

_TOKEN = {"value": None, "expires_at": 0.0}
_TOKEN_LOCK = threading.Lock()


def _get_oauth_token(client_id: str, client_secret: str, user_agent: str) -> str:
    with _TOKEN_LOCK:
        if _TOKEN["value"] and time.time() < _TOKEN["expires_at"] - 60:
            return _TOKEN["value"]
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        req = urllib.request.Request(
            OAUTH_TOKEN_URL,
            data=body,
            headers={
                "Authorization": f"Basic {credentials}",
                "User-Agent": user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Reddit OAuth token request failed with HTTP {e.code}") from e
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Reddit OAuth response contained no access token")
        _TOKEN["value"] = token
        _TOKEN["expires_at"] = time.time() + float(payload.get("expires_in", 3600))
        return token


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
        self._client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
        self._client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
        self._user_agent = os.getenv("REDDIT_USER_AGENT", "").strip() or DEFAULT_USER_AGENT
        self.oauth_enabled = bool(self._client_id and self._client_secret)

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
                if e.code in (403, 404):
                    log.warning("HTTP %d fetching %s", e.code, url)
                    reason = {403: "blocked", 404: "post not found or removed"}
                    raise RuntimeError(f"Reddit RSS returned {e.code} — {reason[e.code]}") from e
                last_error = e
                log.warning("HTTP %d fetching %s (attempt %d/%d)", e.code, url, attempt + 1, self.max_retries)
                if e.code == 429 and attempt < self.max_retries - 1:
                    backoff = 5 * (attempt + 1)
                    log.warning("Rate limited by Reddit — backing off %ds", backoff)
                    time.sleep(backoff)
            except (urllib.error.URLError, OSError) as e:
                last_error = e
                log.warning("Network error fetching %s: %s (attempt %d/%d)", url, e, attempt + 1, self.max_retries)
        if isinstance(last_error, urllib.error.HTTPError) and last_error.code == 429:
            raise RuntimeError("Reddit RSS returned 429 — rate limited, try again in a minute") from last_error
        raise RuntimeError(
            f"Reddit RSS unreachable after {self.max_retries} attempts: {last_error}"
        ) from last_error

    def _oauth_json(self, path: str, params: dict | None = None):
        token = _get_oauth_token(self._client_id, self._client_secret, self._user_agent)
        url = f"{OAUTH_API_BASE}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}", "User-Agent": self._user_agent},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                with _TOKEN_LOCK:
                    _TOKEN["value"] = None
                raise RuntimeError("Reddit OAuth token rejected (401) — check credentials") from e
            raise RuntimeError(f"Reddit API returned HTTP {e.code}") from e

    def _collect_comments(self, children: list, out: list[dict], cap: int = 200) -> None:
        for child in children:
            if len(out) >= cap:
                return
            if child.get("kind") != "t1":
                continue
            data = child.get("data", {})
            body = (data.get("body") or "").strip()
            if body and body not in ("[removed]", "[deleted]"):
                out.append({
                    "author": data.get("author") or "unknown",
                    "score": int(data.get("score") or 0),
                    "text": body,
                })
            replies = data.get("replies")
            if isinstance(replies, dict):
                self._collect_comments(replies.get("data", {}).get("children", []), out, cap)

    @staticmethod
    def _post_id(url: str) -> str:
        parts = [p for p in urlparse(url).path.split("/") if p]
        if "comments" in parts:
            idx = parts.index("comments")
            if idx + 1 < len(parts) and re.fullmatch(r"[A-Za-z0-9]+", parts[idx + 1]):
                return parts[idx + 1]
        raise ValueError(f"Not a valid Reddit post URL: {url}")

    def fetch_post(self, url: str) -> RedditPost:
        if self.oauth_enabled:
            try:
                return self._fetch_post_oauth(url)
            except Exception as e:
                log.warning("Reddit OAuth fetch failed (%s) — falling back to RSS", e)
        return self._fetch_post_rss(url)

    def _fetch_post_oauth(self, url: str) -> RedditPost:
        data = self._oauth_json(
            f"/comments/{self._post_id(url)}",
            {"limit": 200, "sort": "top", "raw_json": 1},
        )
        post = data[0]["data"]["children"][0]["data"]
        comments: list[dict] = []
        self._collect_comments(data[1].get("data", {}).get("children", []), comments)
        text = (post.get("selftext") or "").strip()
        if text in ("[removed]", "[deleted]"):
            text = ""
        permalink = post.get("permalink") or ""
        return RedditPost(
            url=f"{self.BASE}{permalink}" if permalink else url,
            title=(post.get("title") or "").strip(),
            author=post.get("author") or "unknown",
            score=int(post.get("score") or 0),
            text=text,
            comments=comments,
        )

    def _fetch_post_rss(self, url: str) -> RedditPost:
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
        if self.oauth_enabled:
            try:
                return self._fetch_listing_oauth(limit)
            except Exception as e:
                log.warning("Reddit OAuth listing failed (%s) — falling back to RSS", e)
        return self._fetch_listing_rss(limit)

    def _fetch_listing_oauth(self, limit: int) -> list[dict]:
        payload = self._oauth_json("/r/all/top", {"t": "day", "limit": limit, "raw_json": 1})
        posts: list[dict] = []
        for child in payload.get("data", {}).get("children", []):
            post = child.get("data", {})
            permalink = post.get("permalink") or ""
            if not permalink:
                continue
            posts.append({
                "url": f"{self.BASE}{permalink}",
                "title": (post.get("title") or "Untitled").strip(),
                "score": int(post.get("score") or 0),
                "comments": int(post.get("num_comments") or 0),
                "subreddit": post.get("subreddit") or "",
            })
        if not posts:
            raise RuntimeError("No posts found in Reddit listing")
        return posts

    def _fetch_listing_rss(self, limit: int = 10) -> list[dict]:
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
