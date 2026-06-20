import argparse
import logging
import sys

from scraper import RedditScraper
from sentiment import SentimentAnalyzer, EMOTION_LABELS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")


def _print_scores(label: str, scores: dict):
    print(f"  ┌─ {label}")
    for emotion in EMOTION_LABELS:
        bar = "█" * int(scores.get(emotion, 0) * 40)
        print(f"  │  {emotion:>10s}  {scores.get(emotion, 0):.1%}  {bar}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Scrape a Reddit post and run multi-emotion sentiment analysis."
    )
    parser.add_argument("url", help="URL of the Reddit post to analyse")
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds between requests (rate limiting, default: 2.0)",
    )
    args = parser.parse_args()

    scraper = RedditScraper(delay=args.delay)
    analyzer = SentimentAnalyzer()

    print(f"\nFetching: {args.url}\n")
    try:
        post = scraper.fetch_post(args.url)
    except Exception as e:
        log.error("Failed to fetch post: %s", e)
        sys.exit(1)

    print(f"Title:    {post.title}")
    print(f"Author:   {post.author}")
    print(f"Score:    {post.score}")
    print(f"Comments: {len(post.comments)}")
    if post.text:
        print(f"Body:     {post.text[:200]}{'…' if len(post.text) > 200 else ''}")
    print(f"{'─' * 60}")

    print("\nAnalysing sentiment…\n")
    result = analyzer.analyze_post(post.title, post.text, post.comments)

    _print_scores("Title", result["title"])
    _print_scores("Body", result["body"])
    _print_scores("Comments (avg)", result["comments_avg"])
    _print_scores("Aggregated (20/30/50 weighted)", result["aggregated"])

    print(f"  Dominant emotion: {result['dominant_emotion'].upper()}")
    print(f"{'─' * 60}\n")


if __name__ == "__main__":
    main()
