"""Turn crawled pages into findings."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import combinations

from urllib.parse import urlsplit

from .crawl import CrawlResult, Page, norm_url, primary_lang
from .filters import TextFilter, normalize
from .langid import LANGUAGES, detect

SEVERITIES = ("low", "medium", "high")


@dataclass
class Finding:
    type: str             # mixed-language, identical-in-alternates, page-language-mismatch
    severity: str
    url: str
    selector: str
    kind: str
    text: str
    expected: str | None
    detected: str
    confidence: float
    pages: list[str] = field(default_factory=list)
    other_url: str | None = None       # identical-in-alternates: the other language version
    other_selector: str | None = None
    other_lang: str | None = None
    untranslated_on: str | None = None
    linked_from: str | None = None     # redirects-to-other-language: page that links to the URL

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Options:
    threshold: float = 0.8
    languages: str = "site"   # "site", "all" or a comma list such as "en,fr"
    min_words: int = 4
    min_chars: int = 20
    allow: list[str] = field(default_factory=list)


def _snippet(text: str, n: int = 160) -> str:
    return text if len(text) <= n else text[: n - 3].rstrip() + "..."


def candidate_languages(pages: list[Page], setting: str) -> tuple[str, ...]:
    if setting == "all":
        return LANGUAGES
    if setting != "site":
        langs = tuple(l.strip().lower() for l in setting.split(",") if l.strip().lower() in LANGUAGES)
        return langs or LANGUAGES
    declared = {p.lang for p in pages if p.lang in LANGUAGES}
    for p in pages:
        declared |= {primary_lang(h) for h in p.parsed.alternates if primary_lang(h) in LANGUAGES}
    return tuple(l for l in LANGUAGES if l in declared) if len(declared) >= 2 else LANGUAGES


def analyze(crawl: CrawlResult, opts: Options) -> dict:
    flt = TextFilter(opts.allow, opts.min_words, opts.min_chars)
    langs = candidate_languages(crawl.pages, opts.languages)
    stats = {"blocks": 0, "checked": 0, "ignored_short": 0, "ignored_code": 0,
             "unsupported_language": 0, "no_declared_language": 0}
    mixed: dict[tuple, Finding] = {}
    page_rows = []
    page_mismatch: list[Finding] = []
    # normalized text -> first block, per page, for the alternates comparison
    comparable: dict[str, dict[str, tuple]] = {}

    for page in crawl.pages:
        n_findings = 0
        detected_langs: dict[str, int] = {}
        comparable[page.url] = {}
        for block in page.parsed.blocks:
            stats["blocks"] += 1
            res = flt.check(block.text)
            if not res.keep:
                stats["ignored_" + res.reason] += 1
                continue
            key = normalize(block.text)
            comparable[page.url].setdefault(key, (block, res))
            expected = primary_lang(block.lang) or page.lang
            if expected is None:
                stats["no_declared_language"] += 1
                continue
            if expected not in LANGUAGES:
                stats["unsupported_language"] += 1
                continue
            stats["checked"] += 1
            det = detect(res.text, languages=langs, min_confidence=opts.threshold)
            if det.lang != "unknown":
                detected_langs[det.lang] = detected_langs.get(det.lang, 0) + 1
            if det.lang in ("unknown", expected):
                continue
            n_findings += 1
            severity = "medium" if det.confidence >= 0.9 and res.words >= 6 else "low"
            fkey = (key, expected, block.kind)
            if fkey in mixed:
                mixed[fkey].pages.append(page.url)
                continue
            mixed[fkey] = Finding("mixed-language", severity, page.url, block.selector, block.kind,
                                  _snippet(block.text), expected, det.lang, det.confidence, [page.url])
        total = sum(detected_langs.values())
        if page.lang in LANGUAGES and total >= 3:
            top = max(detected_langs, key=detected_langs.get)
            if top != page.lang and detected_langs[top] / total > 0.5:
                page_mismatch.append(Finding(
                    "page-language-mismatch", "high", page.url, "html", "page",
                    f"{detected_langs[top]} of {total} checked blocks read as '{top}'",
                    page.lang, top, round(detected_langs[top] / total, 4), [page.url]))
        page_rows.append({"url": page.url, "lang": page.declared, "primary_lang": page.lang,
                          "lang_source": page.lang_source,
                          "blocks": len(page.parsed.blocks), "findings": n_findings,
                          "alternates": page.parsed.alternates})

    identical = _identical(crawl.pages, comparable, langs)
    findings = page_mismatch + identical + list(mixed.values()) + _language_redirects(crawl)
    order = {s: i for i, s in enumerate(reversed(SEVERITIES))}
    findings.sort(key=lambda f: (order[f.severity], f.type, f.url))
    counts = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITIES}
    return {
        "languages": list(langs),
        "pages": page_rows,
        "skipped": [{"url": u, "reason": r} for u, r in crawl.skipped],
        "requests": crawl.requests,
        "stats": stats,
        "counts": counts,
        "findings": findings,
    }


def _identical(pages: list[Page], comparable: dict, langs: tuple[str, ...]) -> list[Finding]:
    by_url = {p.url: p for p in pages}
    pairs: set[tuple[str, str]] = set()
    for page in pages:
        group = {page.url} | {norm_url(u) for u in page.parsed.alternates.values()}
        group = sorted(u for u in group if u in by_url)
        for a, b in combinations(group, 2):
            la, lb = by_url[a].lang, by_url[b].lang
            if la and lb and la != lb:
                pairs.add((a, b))

    found: dict[tuple, Finding] = {}
    for a, b in sorted(pairs):
        pa, pb = by_url[a], by_url[b]
        for key in comparable[a].keys() & comparable[b].keys():
            block_a, res = comparable[a][key]
            block_b, _ = comparable[b][key]
            pair_langs = tuple(l for l in (pa.lang, pb.lang) if l in LANGUAGES) or langs
            det = detect(res.text, languages=pair_langs, min_confidence=0.0)
            untranslated = b if det.lang == pa.lang else a if det.lang == pb.lang else None
            fkey = (key, frozenset((pa.lang, pb.lang)))
            if fkey in found:
                found[fkey].pages.extend(u for u in (a, b) if u not in found[fkey].pages)
                continue
            found[fkey] = Finding(
                "identical-in-alternates", "high", a, block_a.selector, block_a.kind,
                _snippet(block_a.text), None, det.lang, det.confidence, [a, b],
                other_url=b, other_selector=block_b.selector, other_lang=pb.lang,
                untranslated_on=untranslated)
            found[fkey].expected = pa.lang
    return list(found.values())


def path_lang(url: str) -> str | None:
    """Language code in the first path segment (/fr/..., /pt-br/...), if any."""
    seg = urlsplit(url).path.strip("/").split("/", 1)[0]
    lang = primary_lang(seg)
    return lang if lang in LANGUAGES and len(seg) in (2, 5) else None


def _language_redirects(crawl: CrawlResult) -> list[Finding]:
    """A /fr/ URL that redirects to an /en/ URL sends French readers to English copy."""
    out = []
    for url, final, referrer in crawl.redirects:
        la, lb = path_lang(url), path_lang(final)
        if la and lb and la != lb:
            out.append(Finding("redirects-to-other-language", "low", url, "a[href]", "link",
                               f"{url} -> {final}", la, lb, 1.0, [url], other_url=final,
                               linked_from=referrer))
    return out


def exit_code(result: dict, fail_on: str) -> int:
    if fail_on == "never":
        return 0
    idx = SEVERITIES.index(fail_on)
    return 1 if any(SEVERITIES.index(f.severity) >= idx for f in result["findings"]) else 0
