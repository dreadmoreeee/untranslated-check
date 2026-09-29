import http.server
import threading

from untranslated_check import USER_AGENT
from untranslated_check.crawl import Crawler, norm_url, primary_lang


def test_hreflang_discovery_and_robots(site):
    res = Crawler(delay=0).crawl([site + "/en/"])
    urls = [p.url for p in res.pages]
    # the hreflang alternate is fetched right after the start page
    assert urls[:2] == [site + "/en/", site + "/fr/"]
    assert set(urls) == {site + "/en/", site + "/fr/", site + "/en/services.html", site + "/fr/services.html"}
    assert (site + "/private/secret.html", "disallowed by robots.txt") in res.skipped
    assert not any("/cdn-cgi/" in u for u in urls + [s[0] for s in res.skipped])


def test_language_from_html_and_hreflang_fallback(site):
    res = Crawler(delay=0).crawl([site + "/fr/services.html"])
    by_url = {p.url: p for p in res.pages}
    fr = by_url[site + "/fr/services.html"]
    assert (fr.lang, fr.declared, fr.lang_source) == ("fr", "fr", "hreflang")
    en = by_url[site + "/en/services.html"]
    assert (en.lang, en.lang_source) == ("en", "html")


def test_max_pages_and_no_crawl(site):
    assert len(Crawler(delay=0, max_pages=1).crawl([site + "/en/"]).pages) == 1
    res = Crawler(delay=0, follow_links=False).crawl([site + "/en/"])
    assert [p.url for p in res.pages] == [site + "/en/", site + "/fr/"]


def _server(handler_cls):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "http://127.0.0.1:%d" % server.server_address[1]


def test_robots_5xx_disallows_everything():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            code = 503 if self.path == "/robots.txt" else 200
            self.send_response(code)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html lang=en><p>hello there friends</p></html>")

        def log_message(self, *a):
            pass

    server, base = _server(H)
    try:
        res = Crawler(delay=0).crawl([base + "/"])
        assert res.pages == []
        assert res.skipped == [(base + "/", "disallowed by robots.txt")]
    finally:
        server.shutdown()


def test_only_get_with_user_agent_and_delay():
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.command, self.path, self.headers.get("User-Agent")))
            if self.path == "/robots.txt":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'<html lang="en"><a href="/two">two</a><a href="/doc.pdf">pdf</a></html>')

        def log_message(self, *a):
            pass

    server, base = _server(H)
    try:
        import time
        t0 = time.monotonic()
        res = Crawler(delay=0.2).crawl([base + "/"])
        elapsed = time.monotonic() - t0
    finally:
        server.shutdown()
    assert [p.url for p in res.pages] == [base + "/", base + "/two"]
    assert {c for c, _, _ in seen} == {"GET"}
    assert all(ua == USER_AGENT for _, _, ua in seen)
    assert [p for _, p, _ in seen] == ["/robots.txt", "/", "/two"]  # the PDF is never requested
    assert elapsed >= 0.4  # three requests, two gaps


def test_helpers():
    assert norm_url("HTTPS://Example.com#x") == "https://example.com/"
    assert primary_lang("fr-CA") == "fr" and primary_lang("pt_BR") == "pt" and primary_lang(None) is None
