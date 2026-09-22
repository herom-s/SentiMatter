import json
import logging
import random
import threading

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

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

COMMENT_LIMIT = 80
BATCH_SIZE = 4
MAX_LENGTH = 512
BATCH_MAX_LENGTH = 192

MODEL_ID = "SamLowe/roberta-base-go_emotions-onnx"
MODEL_FILE = "onnx/model_quantized.onnx"
TOKENIZER_FILE = "onnx/tokenizer.json"
CONFIG_FILE = "onnx/config.json"


def _sigmoid(logits):
    return 1.0 / (1.0 + np.exp(-logits))


class SentimentAnalyzer:
    def __init__(self, model_name=MODEL_ID):
        log.info("Loading emotion model: %s", model_name)
        model_path = hf_hub_download(model_name, MODEL_FILE)
        tokenizer_path = hf_hub_download(model_name, TOKENIZER_FILE)
        config_path = hf_hub_download(model_name, CONFIG_FILE)

        with open(config_path, encoding="utf-8") as f:
            id2label = json.load(f).get("id2label", {})
        self._labels = [id2label[str(i)] for i in range(len(id2label))]

        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._tokenizer.enable_truncation(max_length=MAX_LENGTH)
        self._tokenizer.enable_padding()
        self._lock = threading.Lock()

        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        self._session = ort.InferenceSession(
            model_path, sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._input_names = [i.name for i in self._session.get_inputs()]

    def _score_batch(self, texts: list[str], max_length: int = MAX_LENGTH):
        with self._lock:
            self._tokenizer.enable_truncation(max_length=max_length)
            encodings = self._tokenizer.encode_batch(texts)
            feed = {
                "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
            }
            logits = self._session.run(None, {name: feed[name] for name in self._input_names})[0]
        return _sigmoid(logits)

    def _scores(self, probs) -> dict:
        scores = {label: round(float(p), 4) for label, p in zip(self._labels, probs)}
        for label in EMOTION_LABELS:
            scores.setdefault(label, 0.0)
        return scores

    def analyze(self, text: str) -> dict:
        if not text or not text.strip():
            return {label: 0.0 for label in EMOTION_LABELS}

        return self._scores(self._score_batch([text])[0])

    def analyze_batch(self, texts: list[str]) -> list[dict]:
        cleaned = [t if t and t.strip() else "" for t in texts]
        batch = [t for t in cleaned if t]
        if not batch:
            return [{label: 0.0 for label in EMOTION_LABELS} for _ in texts]

        chunks = [
            self._score_batch(batch[i:i + BATCH_SIZE], BATCH_MAX_LENGTH)
            for i in range(0, len(batch), BATCH_SIZE)
        ]
        probs = np.concatenate(chunks, axis=0) if len(chunks) > 1 else chunks[0]

        all_scores = []
        idx = 0
        for t in cleaned:
            if t:
                all_scores.append(self._scores(probs[idx]))
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
