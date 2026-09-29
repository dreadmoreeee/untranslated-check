import json
import socket

from untranslated_check.cli import main


def test_findings_exit_1_and_markdown(site, capsys):
    code = main([site + "/en/", "--delay", "0", "-q"])
    out = capsys.readouterr().out
    assert code == 1
    assert "## Identical text in language versions (1)" in out
    assert "## Blocks in another language (2)" in out
    assert "disallowed by robots.txt" in out


def test_json_output_file(site, tmp_path):
    out = tmp_path / "report.json"
    code = main([site + "/en/", "--delay", "0", "-q", "--format", "json", "--output", str(out)])
    assert code == 1
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["tool"] == "untranslated-check"
    assert data["counts"] == {"low": 0, "medium": 2, "high": 1}
    types = sorted(f["type"] for f in data["findings"])
    assert types == ["identical-in-alternates", "mixed-language", "mixed-language"]
    f = next(f for f in data["findings"] if f["type"] == "identical-in-alternates")
    assert {"selector", "text", "detected", "expected", "confidence", "other_url"} <= set(f)
    assert len(data["pages"]) == 4


def test_clean_exit_0(site, capsys):
    # services pages are fully translated
    assert main([site + "/en/services.html", "--no-crawl", "--delay", "0", "-q"]) == 0
    # the home pair only has medium/high findings
    assert main([site + "/en/", "--delay", "0", "-q", "--fail-on", "never"]) == 0
    assert main([site + "/en/", "--delay", "0", "-q", "--fail-on", "high"]) == 1
    capsys.readouterr()


def test_allow_option_silences_findings(site, capsys, tmp_path):
    allow = tmp_path / "allow.txt"
    allow.write_text("A developer working on a laptop in a bright office\n", encoding="utf-8")
    code = main([site + "/en/", "--delay", "0", "-q", "--allow-file", str(allow),
                 "--allow", "Our team answers every message within one business day",
                 "--allow", "even during the busy summer season"])
    assert code == 0
    assert "Findings: 0" in capsys.readouterr().out


def test_usage_and_network_errors_exit_2(capsys, tmp_path):
    assert main([]) == 2
    assert main(["ftp://example.com/"]) == 2
    assert main(["http://127.0.0.1/", "--allow-file", str(tmp_path / "missing.txt")]) == 2
    # a port nobody listens on: connection refused
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert main([f"http://127.0.0.1:{port}/", "--delay", "0", "-q", "--timeout", "2"]) == 2
    try:
        main(["--fail-on", "bogus", "http://x.test/"])
    except SystemExit as e:
        assert e.code == 2
    capsys.readouterr()


def test_detect_flag(capsys):
    assert main(["--detect", "Nous concevons des sites web pour les entreprises locales."]) == 0
    assert capsys.readouterr().out.startswith("fr ")
