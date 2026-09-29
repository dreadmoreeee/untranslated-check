from untranslated_check.filters import DEFAULT_ALLOW, TextFilter, load_allow_file, normalize


def test_short_strings_are_ignored():
    f = TextFilter([], min_words=4, min_chars=20)
    assert f.check("Read more").reason == "short"
    assert f.check("Contact us today please").keep is True
    assert TextFilter([], min_words=2, min_chars=5).check("Read more").keep is True


def test_allowlist_removes_brand_names():
    f = TextFilter(DEFAULT_ALLOW)
    res = f.check("DeMark Studio, Miramichi, New Brunswick")
    assert not res.keep and res.reason == "short"
    res = f.check("Web design by DeMark Studio in Miramichi for local shops")
    assert res.keep
    assert "DeMark" not in res.text and "Miramichi" not in res.text
    # case-insensitive and whole words only
    assert TextFilter(["Acme"]).strip("ACME builds acmeish tools") == "builds acmeish tools"


def test_urls_emails_numbers_prices_removed():
    f = TextFilter([])
    text = "Write to hello@example.com or visit https://example.com/x, from $1,200 or 99 % 2026"
    assert f.strip(text) == "Write to or visit from or"


def test_code_is_ignored():
    f = TextFilter([])
    assert f.check("const x = useState(); window.location.href = url;").reason == "code"
    assert f.check("pip install untranslated_check --upgrade now please").keep  # one code token of six


def test_allow_file(tmp_path):
    p = tmp_path / "allow.txt"
    p.write_text("# brands\nAcme Corp\n\n  Widget Pro  \n", encoding="utf-8")
    assert load_allow_file(str(p)) == ["Acme Corp", "Widget Pro"]


def test_normalize():
    assert normalize("  Hello\u00a0World\u2019s   BEST!  ") == "hello world's best"
