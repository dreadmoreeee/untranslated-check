"""Measure the bundled language identifier on tests/data/langid_testset.jsonl.

    python scripts/langid_accuracy.py

Prints accuracy on the full sentences and on their first N words (shorter
strings are harder), per language, plus every confusion.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from untranslated_check.langid import LANGUAGES, detect  # noqa: E402

TESTSET = ROOT / "tests" / "data" / "langid_testset.jsonl"


def run(prefix_words: int | None) -> None:
    items = [json.loads(l) for l in TESTSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = {l: 0 for l in LANGUAGES}
    n = {l: 0 for l in LANGUAGES}
    errors = []
    for it in items:
        text = it["text"] if prefix_words is None else " ".join(it["text"].split()[:prefix_words])
        d = detect(text)
        n[it["lang"]] += 1
        if d.lang == it["lang"]:
            ok[it["lang"]] += 1
        else:
            errors.append(f"    {it['lang']} -> {d.lang} ({d.confidence:.2f}): {text}")
    label = "full sentences" if prefix_words is None else f"first {prefix_words} words"
    total_ok, total = sum(ok.values()), sum(n.values())
    per = "  ".join(f"{l} {ok[l]}/{n[l]}" for l in LANGUAGES)
    print(f"{label:15} {total_ok}/{total} = {100 * total_ok / total:.1f}%   {per}")
    for e in errors:
        print(e)


if __name__ == "__main__":
    for k in (None, 6, 4, 3):
        run(k)
