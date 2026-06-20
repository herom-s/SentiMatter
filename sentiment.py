import logging

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


class SentimentAnalyzer:
    def __init__(self, model_name="SamLowe/roberta-base-go_emotions"):
        log.info("Loading emotion model: %s", model_name)
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

        results = self._pipe(text[:512])[0]
        scores = {item["label"]: round(item["score"], 4) for item in results}

        for label in EMOTION_LABELS:
            scores.setdefault(label, 0.0)

        return scores

    def analyze_batch(self, texts: list[str]) -> list[dict]:
        cleaned = [t[:512] if t and t.strip() else "" for t in texts]
        batch = [t for t in cleaned if t]
        if not batch:
            return [{label: 0.0 for label in EMOTION_LABELS} for _ in texts]

        pipe_results = self._pipe(batch)
        all_scores = []
        idx = 0
        for t in cleaned:
            if t:
                scores = {item["label"]: round(item["score"], 4) for item in pipe_results[idx]}
                for label in EMOTION_LABELS:
                    scores.setdefault(label, 0.0)
                all_scores.append(scores)
                idx += 1
            else:
                all_scores.append({label: 0.0 for label in EMOTION_LABELS})
        return all_scores

    def analyze_post(self, title: str, body: str, comments: list[dict]) -> dict:
        title_scores = self.analyze(title)
        body_scores = self.analyze(body)

        comment_scores = {label: 0.0 for label in EMOTION_LABELS}
        if comments:
            texts = [c["text"] for c in comments]
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
                (title_scores.get(label, 0) * 0.2)
                + (body_scores.get(label, 0) * 0.3)
                + (comment_scores.get(label, 0) * 0.5),
                4,
            )

        return {
            "title": title_scores,
            "body": body_scores,
            "comments_avg": comment_scores,
            "aggregated": aggregated,
            "dominant_emotion": max(aggregated, key=aggregated.get),
        }
