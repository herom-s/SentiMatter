import logging
import random
from functools import lru_cache

import torch
from transformers import pipeline

log = logging.getLogger(__name__)

# GoEmotions 27 emotion categories (plus neutral = 28 total)
# From: https://github.com/google-research/google-research/tree/master/goemotions
EMOTION_LABELS = [
    "admiration", "amusement", "anger", "annoyance", "approval",
    "caring", "confusion", "curiosity", "desire", "disappointment",
    "disapproval", "disgust", "embarrassment", "excitement", "fear",
    "gratitude", "grief", "joy", "love", "nervousness",
    "optimism", "pride", "realization", "relief", "remorse",
    "sadness", "surprise", "neutral",
]

MAX_TOKENS = 384
COMMENT_LIMIT = 80
BATCH_SIZE = 32


def _to_scores(result):
    return {item["label"]: round(item["score"], 4) for item in result}


class SentimentAnalyzer:
    def __init__(self, model_name="SamLowe/roberta-base-go_emotions"):
        log.info("Loading emotion model: %s", model_name)
        torch.set_num_threads(4)
        device = 0 if torch.cuda.is_available() else -1
        self._pipe = pipeline(
            "text-classification",
            model=model_name,
            top_k=None,
            device=device,
        )

    def analyze(self, text: str) -> dict:
        if not text or not text.strip():
            return {label: 0.0 for label in EMOTION_LABELS}

        results = self._pipe(text[:MAX_TOKENS])[0]
        scores = _to_scores(results)

        for label in EMOTION_LABELS:
            scores.setdefault(label, 0.0)

        return scores

    def analyze_batch(self, texts: list[str]) -> list[dict]:
        cleaned = [t[:MAX_TOKENS] if t and t.strip() else "" for t in texts]
        batch = [t for t in cleaned if t]
        if not batch:
            return [{label: 0.0 for label in EMOTION_LABELS} for _ in texts]

        pipe_results = self._pipe(batch, batch_size=BATCH_SIZE)
        all_scores = []
        idx = 0
        for t in cleaned:
            if t:
                scores = _to_scores(pipe_results[idx])
                for label in EMOTION_LABELS:
                    scores.setdefault(label, 0.0)
                all_scores.append(scores)
                idx += 1
            else:
                all_scores.append({label: 0.0 for label in EMOTION_LABELS})
        return all_scores

    def analyze_post(self, title: str, body: str, comments: list[dict], max_comments: int = COMMENT_LIMIT) -> dict:
        title_scores = self.analyze(title)
        body_scores = self.analyze(body)

        comment_scores = {label: 0.0 for label in EMOTION_LABELS}
        if comments:
            sample = random.sample(comments, min(max_comments, len(comments)))
            texts = [c["text"] for c in sample]
            batch_results = self.analyze_batch(texts)
            count = 0
            for cs in batch_results:
                if any(v != 0.0 for v in cs.values()):
                    for label in EMOTION_LABELS:
                        comment_scores[label] += cs.get(label, 0.0)
                    count += 1
            if count > 0:
                for label in EMOTION_LABELS:
                    comment_scores[label] /= count

        aggregated = {}
        for label in EMOTION_LABELS:
            aggregated[label] = round(
                title_scores.get(label, 0) * 0.2
                + body_scores.get(label, 0) * 0.3
                + comment_scores.get(label, 0) * 0.5,
                4,
            )

        return {
            "title": title_scores,
            "body": body_scores,
            "comments_avg": comment_scores,
            "aggregated": aggregated,
            "dominant_emotion": max(aggregated, key=aggregated.get),
        }
