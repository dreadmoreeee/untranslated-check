"""Polite discovery of pages: hreflang alternates first, then same-host links.

GET only, one request at a time, a fixed delay between requests (or the
robots.txt Crawl-delay when larger), RFC 9309 robots.txt matching.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from . import USER_AGENT, rfc9309
from .extract import ParsedPage, parse_page

MAX_BYTES = 3 * 1024 * 1024
SKIP_EXT = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".ico", ".zip",
            ".gz", ".css", ".js", ".json", ".xml", ".txt", ".mp4", ".mp3", ".webm", ".woff",
            ".woff2", ".ttf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".rss")


def norm_url(url: str) -> str:
    """Drop the fragment, lower-case scheme and host, give an empty path '/'."""
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", p.query, ""))


def _base_domain(host: str) -> str:
    host = host.split(":")[0]
    return host[4:] if host.startswith("www.") else host


def primary_lang(tag: str | None) -> str | None:
    if not tag:
        return None
    return tag.strip().replace("_", "-").split("-")[0].lower() or None


@dataclass
class Page:
    url: str
    status: int
    parsed: ParsedPage
    lang: str | None = None          # primary subtag, e.g. "fr"
    declared: str | None = None      # full tag as declared, e.g. "fr-CA"
    lang_source: str | None = None   # "html" or "hreflang"


@dataclass
class CrawlResult:
    pages: list[Page] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    redirects: list[tuple[str, str, str | None]] = field(default_factory=list)  # (url, final, linked from)
    requests: int = 0


class Crawler:
    def __init__(self, max_pages: int = 30, delay: float = 1.0, timeout: float = 15.0,
                 user_agent: str = USER_AGENT, follow_links: bool = True, log=None) -> None:
        self.max_pages = max_pages
        self.delay = delay
        self.timeout = timeout
        self.user_agent = user_agent
        self.follow_links = follow_links
        self.log = log or (lambda msg: None)
        self._last = 0.0
        self._robots: dict[str, rfc9309.RobotsTxt] = {}
        self.result = CrawlResult()

    # -- network -----------------------------------------------------------
    def _wait(self, extra: float | None = None) -> None:
        pause = max(self.delay, min(extra or 0.0, 10.0))
        if self._last:
            # time.sleep can return slightly early on Windows, so re-check the clock
            while True:
                remaining = pause - (time.monotonic() - self._last)
                if remaining <= 0:
                    break
                time.sleep(remaining)
        self._last = time.monotonic()

    def robots(self, url: str) -> rfc9309.RobotsTxt:
        p = urlsplit(url)
        key = f"{p.scheme}://{p.netloc}"
        if key not in self._robots:
            self._wait()
            self.result.requests += 1
            self._robots[key] = rfc9309.fetch(key, self.user_agent, self.timeout)
        return self._robots[key]

    def fetch(self, url: str) -> tuple[str, int, str, str]:
        """GET a page. Returns (final_url, status, content_type, text)."""
        self._wait(self.robots(url).crawl_delay(self.user_agent))
        self.result.requests += 1
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent,
                                                   "Accept": "text/html,application/xhtml+xml"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                ctype = resp.headers.get("Content-Type", "")
                raw = resp.read(MAX_BYTES)
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.geturl(), resp.status, ctype, raw.decode(charset, "replace")
        except urllib.error.HTTPError as e:
            return url, e.code, e.headers.get("Content-Type", "") if e.headers else "", ""

    # -- discovery ---------------------------------------------------------
    def _allowed_host(self, host: str, hosts: set[str], via_hreflang: bool) -> bool:
        if host in hosts:
            return True
        if via_hreflang:
            base = {_base_domain(h) for h in hosts}
            b = _base_domain(host)
            return any(b == d or b.endswith("." + d) for d in base)
        return False

    @staticmethod
    def _crawlable(url: str) -> bool:
        p = urlsplit(url)
        if p.scheme not in ("http", "https"):
            return False
        path = p.path.lower()
        if "/cdn-cgi/" in path:
            return False
        return not path.endswith(SKIP_EXT)

    def crawl(self, start_urls: list[str]) -> CrawlResult:
        res = self.result
        queue: deque[tuple[str, str | None]] = deque()  # (url, page that linked to it)
        seen: set[str] = set()
        hosts = {urlsplit(u).netloc.lower() for u in start_urls}
        for u in start_urls:
            n = norm_url(u)
            if n not in seen:
                seen.add(n)
                queue.append((n, None))

        loaded = 0
        while queue and loaded < self.max_pages:
            url, referrer = queue.popleft()
            if not self._crawlable(url):
                res.skipped.append((url, "not crawlable"))
                continue
            if not self.robots(url).can_fetch(self.user_agent, url):
                res.skipped.append((url, "disallowed by robots.txt"))
                self.log(f"robots.txt disallows {url}")
                continue
            loaded += 1
            try:
                final, status, ctype, text = self.fetch(url)
            except (urllib.error.URLError, OSError, ValueError) as e:
                reason = getattr(e, "reason", e)
                res.skipped.append((url, f"network error: {reason}"))
                self.log(f"error {url}: {reason}")
                continue
            final = norm_url(final)
            self.log(f"{status} {url}" + (f" -> {final}" if final != url else ""))
            if final != url:
                res.redirects.append((url, final, referrer))
                if final in seen:
                    res.skipped.append((url, f"redirects to {final} (already queued)"))
                    continue
                seen.add(final)
            if status >= 400:
                res.skipped.append((url, f"HTTP {status}"))
                continue
            if "html" not in ctype.lower():
                res.skipped.append((url, f"not HTML ({ctype or 'no content type'})"))
                continue
            parsed = parse_page(text, final)
            page = Page(final, status, parsed)
            self._set_lang(page)
            res.pages.append(page)

            # hreflang alternates jump the queue so language pairs are complete.
            for target in reversed(list(parsed.alternates.values())):
                n = norm_url(target)
                if n in seen:
                    queued = next((item for item in queue if item[0] == n), None)
                    if queued is not None:  # already queued as a plain link: move it up
                        queue.remove(queued)
                        queue.appendleft(queued)
                    continue
                if self._allowed_host(urlsplit(n).netloc, hosts, True):
                    seen.add(n)
                    hosts.add(urlsplit(n).netloc)
                    queue.appendleft((n, final))
            if self.follow_links:
                page_host = urlsplit(final).netloc
                for link in parsed.links:
                    n = norm_url(link)
                    if n in seen or urlsplit(n).netloc != page_host or not self._crawlable(n):
                        continue
                    seen.add(n)
                    queue.append((n, final))
        if queue:
            self.log(f"stopped at {self.max_pages} pages; {len(queue)} URL(s) not visited")
        return res

    @staticmethod
    def _set_lang(page: Page) -> None:
        if page.parsed.lang:
            page.declared, page.lang_source = page.parsed.lang, "html"
        else:
            for hreflang, target in page.parsed.alternates.items():
                if hreflang != "x-default" and norm_url(target) == page.url:
                    page.declared, page.lang_source = hreflang, "hreflang"
                    break
        page.lang = primary_lang(page.declared)
