"""Build untranslated_check/langid_model.json from scripts/langid_corpus.json.

    python scripts/build_langid.py

The corpus holds hand-written training sentences and stopword lists for each
language. Trigram log-probabilities use add-k smoothing over the shared
trigram vocabulary. The test set in tests/data/ is never used here.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from untranslated_check.langid import LANGUAGES, MODEL_PATH, trigrams, words  # noqa: E402

K = 0.5


def build() -> dict:
    corpus = json.loads((ROOT / "scripts" / "langid_corpus.json").read_text(encoding="utf-8"))
    counts = {l: Counter(trigrams(words(" ".join(corpus["train"][l])))) for l in LANGUAGES}
    vocab = set().union(*counts.values())
    model = {"languages": list(LANGUAGES), "stopwords": {}, "trigrams": {}, "unseen": {}}
    for lang in LANGUAGES:
        c = counts[lang]
        denom = sum(c.values()) + K * len(vocab)
        model["trigrams"][lang] = {t: round(math.log((n + K) / denom), 3) for t, n in sorted(c.items())}
        model["unseen"][lang] = round(math.log(K / denom), 3)
        model["stopwords"][lang] = sorted({w for s in corpus["stopwords"][lang] for w in words(s)})
    return model


if __name__ == "__main__":
    model = build()
    MODEL_PATH.write_text(json.dumps(model, ensure_ascii=True, separators=(",", ":")), encoding="ascii")
    print(f"wrote {MODEL_PATH} ({MODEL_PATH.stat().st_size} bytes)")
