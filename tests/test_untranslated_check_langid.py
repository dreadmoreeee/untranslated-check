from pathlib import Path

from untranslated_check.langid import LANGUAGES, detect, evaluate

TESTSET = Path(__file__).resolve().parent / "data" / "langid_testset.jsonl"


def test_testset_is_balanced():
    lines = TESTSET.read_text(encoding="utf-8").splitlines()
    for lang in LANGUAGES:
        assert sum(f'"lang": "{lang}"' in line for line in lines) >= 40


def test_accuracy_on_bundled_testset():
    r = evaluate(TESTSET)
    assert r["total"] >= 200
    assert r["accuracy"] >= 0.90
    for lang in LANGUAGES:
        assert r["per_language"][lang] >= 0.85, (lang, r["confusion"][lang])


def test_accuracy_on_short_prefixes():
    # First five words only: harder, still expected to be mostly right.
    import json
    ok = total = 0
    for line in TESTSET.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        text = " ".join(item["text"].split()[:5])
        ok += detect(text).lang == item["lang"]
        total += 1
    assert ok / total >= 0.90


def test_examples_and_confidence():
    d = detect("Nous concevons des sites web rapides pour les entreprises locales.")
    assert d.lang == "fr" and d.confidence >= 0.9
    assert detect("Wir bauen schnelle Webseiten f\u00fcr kleine Unternehmen.").lang == "de"
    assert detect("N\u00e3o se preocupe, n\u00f3s cuidamos de tudo para voc\u00ea.").lang == "pt"
    assert detect("\u00bfD\u00f3nde est\u00e1 la estaci\u00f3n de tren m\u00e1s cercana?").lang == "es"


def test_unknown_when_no_text_or_low_confidence():
    assert detect("").lang == "unknown"
    assert detect("12345 !!!").lang == "unknown"
    d = detect("Stripe", min_confidence=0.99)
    assert d.lang == "unknown"
    assert d.best in LANGUAGES


def test_candidate_languages_restrict_result():
    d = detect("Web design in Miramichi", languages=("en", "fr"))
    assert set(d.probabilities) == {"en", "fr"}
    assert d.lang == "en"
