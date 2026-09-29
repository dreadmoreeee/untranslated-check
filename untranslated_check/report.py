"""Markdown and JSON reports."""
from __future__ import annotations

import json

from . import __version__


def _cell(text: str, n: int = 90) -> str:
    text = text if len(text) <= n else text[: n - 3].rstrip() + "..."
    return text.replace("|", "\\|").replace("\n", " ")


def to_json(result: dict, start_urls: list[str]) -> str:
    data = dict(result)
    data["findings"] = [f.to_dict() for f in result["findings"]]
    data = {"tool": "untranslated-check", "version": __version__, "start_urls": start_urls, **data}
    return json.dumps(data, indent=2, ensure_ascii=False)


def to_markdown(result: dict, start_urls: list[str]) -> str:
    f_all = result["findings"]
    counts = result["counts"]
    langs = {}
    for p in result["pages"]:
        key = p["primary_lang"] or "?"
        langs[key] = langs.get(key, 0) + 1
    out = [
        "# untranslated-check report",
        "",
        f"Start: {', '.join(start_urls)}",
        f"Pages checked: {len(result['pages'])} ("
        + ", ".join(f"{k}: {v}" for k, v in sorted(langs.items())) + f"), requests: {result['requests']}, "
        f"languages compared: {', '.join(result['languages'])}",
        f"Text blocks: {result['stats']['blocks']} ({result['stats']['checked']} checked, "
        f"{result['stats']['ignored_short']} too short, {result['stats']['ignored_code']} code)",
        f"Findings: {len(f_all)} (high {counts['high']}, medium {counts['medium']}, low {counts['low']})",
    ]

    mismatch = [f for f in f_all if f.type == "page-language-mismatch"]
    if mismatch:
        out += ["", f"## Pages in the wrong language ({len(mismatch)})", "",
                "| Page | Declared | Reads as | Detail |", "|---|---|---|---|"]
        out += [f"| {f.url} | {f.expected} | {f.detected} | {f.text} |" for f in mismatch]

    identical = [f for f in f_all if f.type == "identical-in-alternates"]
    out += ["", f"## Identical text in language versions ({len(identical)})", ""]
    if identical:
        out += ["| Pages | Langs | Where | Text | Reads as | Untranslated on |",
                "|---|---|---|---|---|---|"]
        for f in identical:
            extra = f" (+{len(f.pages) - 2} more)" if len(f.pages) > 2 else ""
            out.append(f"| {f.url} / {f.other_url}{extra} | {f.expected}/{f.other_lang} | "
                       f"`{_cell(f.selector, 60)}` ({f.kind}) | {_cell(f.text)} | "
                       f"{f.detected} {f.confidence:.2f} | {f.untranslated_on or '?'} |")
    else:
        out.append("None.")

    mixed = [f for f in f_all if f.type == "mixed-language"]
    out += ["", f"## Blocks in another language ({len(mixed)})", ""]
    if mixed:
        out += ["| Sev | Page | Where | Expected | Detected | Conf | Text |",
                "|---|---|---|---|---|---|---|"]
        for f in mixed:
            extra = f" (+{len(f.pages) - 1} more)" if len(f.pages) > 1 else ""
            out.append(f"| {f.severity} | {f.url}{extra} | `{_cell(f.selector, 60)}` ({f.kind}) | "
                       f"{f.expected} | {f.detected} | {f.confidence:.2f} | {_cell(f.text)} |")
    else:
        out.append("None.")

    redirects = [f for f in f_all if f.type == "redirects-to-other-language"]
    if redirects:
        out += ["", f"## Links that switch language ({len(redirects)})", "",
                "| Link | Redirects to | Linked from |", "|---|---|---|"]
        out += [f"| {f.url} | {f.other_url} | {f.linked_from or '-'} |" for f in redirects]

    out += ["", "## Pages", "", "| URL | Lang | From | Blocks | Findings |", "|---|---|---|---|---|"]
    for p in result["pages"]:
        out.append(f"| {p['url']} | {p['lang'] or '-'} | {p['lang_source'] or '-'} | {p['blocks']} | {p['findings']} |")
    shown = {f.url for f in redirects}
    skipped = [f"- {s['url']}: {s['reason']}" for s in result["skipped"] if s["url"] not in shown]
    if skipped:
        out += ["", "## Skipped", ""] + skipped
    return "\n".join(out) + "\n"
