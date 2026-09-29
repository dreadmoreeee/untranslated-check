"""Small language identifier for en, fr, es, pt and de.

Two signals are combined:

- stopwords: the share of the words that are common function words of a language;
- character trigrams: the average log-probability of the text's trigrams under a
  profile built from a short training corpus (see scripts/build_langid.py).

Both are turned into one score per language, scaled by how much text there is
(short strings carry less evidence), and normalised with a softmax. The top
probability is the confidence; below ``min_confidence`` the answer is 'unknown'.
The model lives in langid_model.json next to this file.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

LANGUAGES = ("en", "fr", "es", "pt", "de")
MODEL_PATH = Path(__file__).with_name("langid_model.json")

# Weights of the two signals and how evidence grows with the number of words.
TRIGRAM_WEIGHT = 1.0
STOPWORD_WEIGHT = 3.0
EVIDENCE_CAP = 25

_WORD = re.compile(r"[^\W\d_]+")


def words(text: str) -> list[str]:
    """Lower-cased alphabetic words; apostrophes and hyphens split words (l'eau -> l, eau)."""
    return _WORD.findall(unicodedata.normalize("NFC", text).lower())


def trigrams(ws: list[str]):
    for w in ws:
        padded = f" {w} "
        for i in range(len(padded) - 2):
            yield padded[i:i + 3]


@dataclass
class _Model:
    stopwords: dict[str, frozenset]
    trigrams: dict[str, dict[str, float]]
    unseen: dict[str, float]


@lru_cache(maxsize=None)
def _load(path: str = str(MODEL_PATH)) -> _Model:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return _Model(
        stopwords={l: frozenset(v) for l, v in data["stopwords"].items()},
        trigrams=data["trigrams"],
        unseen=data["unseen"],
    )


@dataclass
class Detection:
    lang: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)

    @property
    def best(self) -> str:
        """Most likely language even when the result is 'unknown'."""
        if not self.probabilities:
            return "unknown"
        return max(self.probabilities, key=self.probabilities.get)


def detect(text: str, min_confidence: float = 0.5, languages=None) -> Detection:
    """Return the language of ``text`` and a confidence in [0, 1].

    ``languages`` limits the candidates (e.g. the languages a site is published in).
    """
    model = _load()
    ws = words(text)
    candidates = [l for l in (languages or LANGUAGES) if l in LANGUAGES] or list(LANGUAGES)
    if not ws:
        return Detection("unknown", 0.0, {})
    tris = list(trigrams(ws))
    evidence = min(len(ws), EVIDENCE_CAP) ** 0.5 * 2.0
    logits = {}
    for lang in candidates:
        table, floor = model.trigrams[lang], model.unseen[lang]
        tri_mean = sum(table.get(t, floor) for t in tris) / len(tris)
        stop_share = sum(1 for w in ws if w in model.stopwords[lang]) / len(ws)
        logits[lang] = evidence * (TRIGRAM_WEIGHT * tri_mean + STOPWORD_WEIGHT * stop_share)
    top = max(logits.values())
    exp = {l: math.exp(v - top) for l, v in logits.items()}
    total = sum(exp.values())
    probs = {l: round(v / total, 4) for l, v in exp.items()}
    lang = max(probs, key=probs.get)
    conf = probs[lang]
    return Detection(lang if conf >= min_confidence else "unknown", conf, probs)


def evaluate(path: str | Path, min_confidence: float = 0.5) -> dict:
    """Accuracy on a JSONL file of {"lang": ..., "text": ...} lines.

    'unknown' counts as wrong. Returns overall and per-language accuracy and a
    confusion table {expected: {predicted: count}}.
    """
    confusion: dict[str, dict[str, int]] = {}
    total = correct = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            pred = detect(item["text"], min_confidence).lang
            row = confusion.setdefault(item["lang"], {})
            row[pred] = row.get(pred, 0) + 1
            total += 1
            correct += pred == item["lang"]
    per_lang = {l: round(row.get(l, 0) / sum(row.values()), 4) for l, row in confusion.items()}
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "per_language": per_lang,
        "confusion": confusion,
    }
