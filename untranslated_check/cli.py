"""Command line interface.

Exit codes: 0 = no finding at or above --fail-on, 1 = findings at or above
--fail-on, 2 = usage error or no page could be fetched.
"""
from __future__ import annotations

import argparse
import sys

from . import USER_AGENT, __version__
from .check import Options, analyze, exit_code
from .crawl import Crawler
from .filters import DEFAULT_ALLOW, load_allow_file
from .langid import detect
from .report import to_json, to_markdown


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="untranslated-check",
        description="Find untranslated or mixed-language text on multilingual sites (en, fr, es, pt, de).",
        epilog="Exit codes: 0 clean, 1 findings at or above --fail-on, 2 usage or network error.",
    )
    p.add_argument("urls", nargs="*", metavar="URL", help="start page(s); hreflang alternates are followed")
    p.add_argument("--max-pages", type=int, default=30, help="page loads per run (default 30)")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1.0)")
    p.add_argument("--timeout", type=float, default=15.0, help="request timeout in seconds")
    p.add_argument("--no-crawl", action="store_true", help="only follow hreflang alternates, not links")
    p.add_argument("--threshold", type=float, default=0.8,
                   help="minimum language-ID confidence to report a block (default 0.8)")
    p.add_argument("--languages", default="site",
                   help="candidate languages: 'site' (declared on the crawled pages, default), 'all', or e.g. 'en,fr'")
    p.add_argument("--min-words", type=int, default=4, help="ignore blocks with fewer words (default 4)")
    p.add_argument("--min-chars", type=int, default=20, help="ignore blocks shorter than this (default 20)")
    p.add_argument("--allow", action="append", default=[], metavar="TERM",
                   help="brand or proper noun to ignore (repeatable)")
    p.add_argument("--allow-file", action="append", default=[], metavar="PATH",
                   help="file with one allowed term per line")
    p.add_argument("--no-default-allow", action="store_true", help="do not use the built-in allowlist")
    p.add_argument("--format", choices=("md", "json"), default="md", help="report format (default md)")
    p.add_argument("--output", "-o", help="write the report to this file instead of stdout")
    p.add_argument("--fail-on", choices=("low", "medium", "high", "never"), default="medium",
                   help="exit 1 when a finding has this severity or higher (default medium)")
    p.add_argument("--user-agent", default=USER_AGENT, help=argparse.SUPPRESS)
    p.add_argument("--detect", metavar="TEXT", help="print the detected language of TEXT and exit")
    p.add_argument("--quiet", "-q", action="store_true", help="no progress on stderr")
    p.add_argument("--version", action="version", version=f"untranslated-check {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.detect is not None:
        d = detect(args.detect)
        probs = ", ".join(f"{k} {v:.2f}" for k, v in sorted(d.probabilities.items(), key=lambda kv: -kv[1]))
        print(f"{d.lang} {d.confidence:.2f}  ({probs})")
        return 0
    if not args.urls:
        parser.print_usage(sys.stderr)
        print("untranslated-check: error: give at least one URL (or --detect TEXT)", file=sys.stderr)
        return 2
    if args.max_pages < 1 or args.delay < 0 or not 0 <= args.threshold <= 1:
        print("untranslated-check: error: bad --max-pages, --delay or --threshold", file=sys.stderr)
        return 2
    for u in args.urls:
        if not u.startswith(("http://", "https://")):
            print(f"untranslated-check: error: not an http(s) URL: {u}", file=sys.stderr)
            return 2

    allow = [] if args.no_default_allow else list(DEFAULT_ALLOW)
    allow += args.allow
    try:
        for path in args.allow_file:
            allow += load_allow_file(path)
    except OSError as e:
        print(f"untranslated-check: error: cannot read allow file: {e}", file=sys.stderr)
        return 2

    log = (lambda msg: None) if args.quiet else (lambda msg: print(msg, file=sys.stderr))
    crawler = Crawler(max_pages=args.max_pages, delay=args.delay, timeout=args.timeout,
                      user_agent=args.user_agent, follow_links=not args.no_crawl, log=log)
    crawl = crawler.crawl(args.urls)
    if not crawl.pages:
        for url, reason in crawl.skipped:
            print(f"untranslated-check: {url}: {reason}", file=sys.stderr)
        print("untranslated-check: error: no page could be checked", file=sys.stderr)
        return 2

    opts = Options(threshold=args.threshold, languages=args.languages, min_words=args.min_words,
                   min_chars=args.min_chars, allow=allow)
    result = analyze(crawl, opts)
    text = to_json(result, args.urls) if args.format == "json" else to_markdown(result, args.urls)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return exit_code(result, args.fail_on)


if __name__ == "__main__":
    sys.exit(main())
