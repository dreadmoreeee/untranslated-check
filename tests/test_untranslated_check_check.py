from untranslated_check.check import Options, analyze, candidate_languages, exit_code
from untranslated_check.crawl import Crawler, CrawlResult, Page
from untranslated_check.extract import parse_page
from untranslated_check.filters import DEFAULT_ALLOW

UNTRANSLATED = "Our team answers every message within one business day, even during the busy summer season."


def _run(site, **kw):
    crawl = Crawler(delay=0).crawl([site + "/en/"])
    return analyze(crawl, Options(allow=list(DEFAULT_ALLOW), **kw))


def test_identical_block_in_alternates(site):
    r = _run(site)
    same = [f for f in r["findings"] if f.type == "identical-in-alternates"]
    assert len(same) == 1
    f = same[0]
    assert f.text == UNTRANSLATED
    assert f.severity == "high"
    assert {f.url, f.other_url} == {site + "/en/", site + "/fr/"}
    assert f.selector == f.other_selector == "body > main > p:nth-of-type(2)"
    assert f.detected == "en"
    assert f.untranslated_on == site + "/fr/"


def test_mixed_language_blocks(site):
    r = _run(site)
    mixed = {f.text: f for f in r["findings"] if f.type == "mixed-language"}
    assert set(mixed) == {UNTRANSLATED, "A developer working on a laptop in a bright office"}
    alt = mixed["A developer working on a laptop in a bright office"]
    assert (alt.url, alt.kind, alt.selector) == (site + "/fr/", "attr:alt", "body > main > img")
    assert (alt.expected, alt.detected) == ("fr", "en")
    assert alt.confidence >= 0.8
    # nothing from <pre>, hidden elements, translate="no" or the allowlisted footer line
    texts = " ".join(mixed)
    assert "hidden" not in texts and "install script" not in texts and "slogan" not in texts
    assert r["languages"] == ["en", "fr"]


def test_allowlist_and_min_words_change_results(site):
    # without the default allowlist the brand line is long enough to be compared
    crawl = Crawler(delay=0).crawl([site + "/en/"])
    r = analyze(crawl, Options(allow=[], min_words=3, min_chars=10))
    same = {f.text for f in r["findings"] if f.type == "identical-in-alternates"}
    assert "DeMark Studio, Miramichi, New Brunswick" in same
    r = analyze(crawl, Options(allow=["summer season", "business day"], min_words=12))
    assert not [f for f in r["findings"] if f.type == "identical-in-alternates"]


def _page(url, lang, html):
    p = Page(url, 200, parse_page(html, url))
    p.lang = p.declared = lang
    p.lang_source = "html"
    return p


def test_duplicates_are_merged_and_page_mismatch():
    footer = "<footer><p>We answer every message within one business day, always.</p></footer>"
    body = ("<p>Nous concevons des sites web rapides pour les entreprises locales.</p>" + footer)
    english = ("<p>This whole page was copied from the English version by mistake.</p>"
               "<p>Nobody translated the second paragraph of this page either.</p>"
               "<p>And the third paragraph is still written in English too.</p>")
    crawl = CrawlResult(pages=[
        _page("https://x.test/fr/a", "fr", body),
        _page("https://x.test/fr/b", "fr", body),
        _page("https://x.test/fr/c", "fr", english),
    ])
    r = analyze(crawl, Options(languages="en,fr"))
    mixed = [f for f in r["findings"] if f.type == "mixed-language"]
    footer_f = [f for f in mixed if f.text.startswith("We answer")]
    assert len(footer_f) == 1 and footer_f[0].pages == ["https://x.test/fr/a", "https://x.test/fr/b"]
    mismatch = [f for f in r["findings"] if f.type == "page-language-mismatch"]
    assert [f.url for f in mismatch] == ["https://x.test/fr/c"]
    assert exit_code(r, "high") == 1 and exit_code(r, "never") == 0


def test_candidate_languages():
    pages = [_page("https://x.test/en", "en", "<p>x</p>"), _page("https://x.test/es", "es", "<p>x</p>")]
    assert candidate_languages(pages, "site") == ("en", "es")
    assert candidate_languages(pages[:1], "site") == ("en", "fr", "es", "pt", "de")
    assert candidate_languages(pages, "de,pt") == ("de", "pt")


def test_link_that_redirects_to_another_language():
    import http.server
    import threading

    pages = {
        "/fr/": b'<html lang="fr"><p>Bienvenue</p><a href="/fr/tarifs">Tarifs</a></html>',
        "/en/pricing": b'<html lang="en"><p>Pricing</p></html>',
    }

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/fr/tarifs":
                self.send_response(301)
                self.send_header("Location", "/en/pricing")
                self.end_headers()
                return
            body = pages.get(self.path)
            self.send_response(200 if body else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body or b"")

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    try:
        crawl = Crawler(delay=0).crawl([base + "/fr/"])
    finally:
        server.shutdown()
    r = analyze(crawl, Options())
    red = [f for f in r["findings"] if f.type == "redirects-to-other-language"]
    assert len(red) == 1
    f = red[0]
    assert (f.url, f.other_url, f.linked_from) == (base + "/fr/tarifs", base + "/en/pricing", base + "/fr/")
    assert (f.expected, f.detected, f.severity) == ("fr", "en", "low")
    assert exit_code(r, "medium") == 0 and exit_code(r, "low") == 1
