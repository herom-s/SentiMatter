# SentiMatter

Scrape any Reddit post and run a 28-emotion sentiment analysis — no official API required.

## How it works

1. **`scraper.py`** — shells out to `curl` to scrape `old.reddit.com` HTML (bypasses bot detection), parses with BeautifulSoup. Extracts the post title, author, score, body text, and all comment threads.
2. **`sentiment.py`** — runs `SamLowe/roberta-base-go_emotions` via HuggingFace Transformers, scoring text across all 28 GoEmotions categories (admiration, amusement, anger, annoyance, approval, caring, confusion, curiosity, desire, disappointment, disapproval, disgust, embarrassment, excitement, fear, gratitude, grief, joy, love, nervousness, optimism, pride, realization, relief, remorse, sadness, surprise, neutral).
3. **`main.py`** — CLI that fetches a post, runs sentiment per-section (title / body / comments avg), and prints an aggregated 20/30/50 weighted result with a visual bar chart.

## Usage

```bash
# Create venv & install
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run
python main.py "https://www.reddit.com/r/pics/comments/1uaw9hw/..." --delay 4.0
```

The `--delay` flag controls the gap between requests (Reddit rate-limits aggressively).

## Requirements

- Python 3.10+
- `curl` on `$PATH`
- Internet connection (model downloads on first run, ~500 MB)
