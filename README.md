# untranslated-check

Finds **untranslated or mixed-language text** on multilingual websites (English, French, Spanish, Portuguese, German) and fails CI when it does.

```
untranslated-check https://example.com/en/ --fail-on medium
```

Checking by eye misses things. A French page can keep one English paragraph, an English `alt` text or an English meta description, and nobody notices because the rest of the page is French. This tool reads every page the way a checker would:

- **Discovery**: starts from your URL(s), follows `<link rel="alternate" hreflang>` first so language pairs are complete, then same-host links. Stops at 30 page loads (`--max-pages`). Respects robots.txt with RFC 9309 matching (longest rule wins), skips `/cdn-cgi/`, sends GET only, one request at a time, 1 s apart.
- **Extraction**: headings, paragraphs, list items, buttons, labels and standalone link text, plus `alt`, `title`, `aria-label`, `placeholder`, `<title>` and the meta description. Each one gets a **CSS selector** so you can find it. Script, style, noscript, code, pre and hidden elements are left out, and so is anything marked `translate="no"` or `class="notranslate"`.
- **Language ID**: a small bundled model (stopwords plus character trigrams, stored as JSON) that returns a language and a confidence, or `unknown` when it is not sure.
- **Expected language**: the nearest `lang` attribute (so `<a lang="fr">Français</a>` on an English page is fine). If there is none, the `hreflang` entry that points to the page itself is used.
- **Identical blocks across language versions**: the same text on `/en/` and `/fr/` is the strongest sign that something was never translated. These are reported separately, as **high**.
- **Links that switch language**: a `/fr/...` link that redirects to an `/en/...` page is reported as **low**.
- **Ignored**: brand names and proper nouns (built-in allowlist, `--allow`, `--allow-file`), emails, URLs, numbers and prices, code, and short strings (fewer than 4 words or 20 characters by default).
- No dependencies. Standard library only, Python 3.10+.

## Measured result

On my own sites, run politely: at most 30 page loads per run, 1 s apart, GET only.

**demarkstudio.ca (EN/FR).** The three French local pages and their English twins are fully translated, with no English block in French and no identical text across a pair. The crawl did find that the French footer and navigation link to 21 `/fr/...` URLs that permanently redirect to English pages. French is only published for the local pages, so this is intended, but a French reader who clicks "Tarifs" lands on English. The report was trimmed (full file in [examples/report-demarkstudio.md](examples/report-demarkstudio.md)):

```
$ python -m untranslated_check https://demarkstudio.ca/fr/conception-web/miramichi https://demarkstudio.ca/fr/conception-web/moncton https://demarkstudio.ca/fr/conception-web/fredericton https://demarkstudio.ca/en/ --output examples/report-demarkstudio.md -q
$ echo $?
0
$ cat examples/report-demarkstudio.md
# untranslated-check report

Start: https://demarkstudio.ca/fr/conception-web/miramichi, https://demarkstudio.ca/fr/conception-web/moncton, https://demarkstudio.ca/fr/conception-web/fredericton, https://demarkstudio.ca/en/
Pages checked: 9 (en: 6, fr: 3), requests: 31, languages compared: en, fr
Text blocks: 1301 (517 checked, 773 too short, 11 code)
Findings: 21 (high 0, medium 0, low 21)

## Identical text in language versions (0)

None.

## Blocks in another language (0)

None.

## Links that switch language (21)

| Link | Redirects to | Linked from |
|---|---|---|
| https://demarkstudio.ca/fr/ | https://demarkstudio.ca/en/ | https://demarkstudio.ca/fr/conception-web/miramichi |
| https://demarkstudio.ca/fr/a-propos | https://demarkstudio.ca/en/about | https://demarkstudio.ca/fr/conception-web/miramichi |
| https://demarkstudio.ca/fr/changer | https://demarkstudio.ca/en/switching | https://demarkstudio.ca/fr/conception-web/miramichi |
[... 18 more rows ...]

## Pages

| URL | Lang | From | Blocks | Findings |
|---|---|---|---|---|
| https://demarkstudio.ca/fr/conception-web/miramichi | fr | html | 92 | 0 |
| https://demarkstudio.ca/en/web-design/miramichi | en | html | 92 | 0 |
| https://demarkstudio.ca/fr/conception-web/moncton | fr | html | 95 | 0 |
| https://demarkstudio.ca/en/web-design/moncton | en | html | 95 | 0 |
| https://demarkstudio.ca/fr/conception-web/fredericton | fr | html | 92 | 0 |
| https://demarkstudio.ca/en/web-design/fredericton | en | html | 92 | 0 |
| https://demarkstudio.ca/en/ | en | html | 328 | 0 |
| https://demarkstudio.ca/en/product | en | html | 181 | 0 |
| https://demarkstudio.ca/en/pricing | en | html | 234 | 0 |

## Skipped

- https://demarkstudio.ca/app/login: disallowed by robots.txt
```

**marvin.demarkstudio.ca (EN/ES).** The Spanish home page keeps the four case-study cards and the list of Google certificates in English. Those cards link to case studies that exist only in English and are labelled "(en inglés)", so the detection is right even though the choice was deliberate. The 5 identical blocks are exactly those paragraphs. The 7 **low** findings are **false positives**: tool cards such as `hreflang-check Python · stdlib · 66 pruebas` are mostly package names and technical terms, and the language model has too little real text there to judge. Trimmed report (full file in [examples/report-marvin.md](examples/report-marvin.md)):

```
$ python -m untranslated_check https://marvin.demarkstudio.ca/ https://marvin.demarkstudio.ca/es/ --output examples/report-marvin.md
200 https://marvin.demarkstudio.ca/
200 https://marvin.demarkstudio.ca/es/
200 https://marvin.demarkstudio.ca/work/demark-studio/
200 https://marvin.demarkstudio.ca/work/triple-a-woodworks/
200 https://marvin.demarkstudio.ca/work/stopping-form-spam/
200 https://marvin.demarkstudio.ca/work/auditing-my-own-sites/
$ echo $?
1
$ cat examples/report-marvin.md
# untranslated-check report

Start: https://marvin.demarkstudio.ca/, https://marvin.demarkstudio.ca/es/
Pages checked: 6 (en: 5, es: 1), requests: 7, languages compared: en, es
Text blocks: 527 (321 checked, 201 too short, 5 code)
Findings: 21 (high 5, medium 9, low 7)

## Identical text in language versions (5)

| Pages | Langs | Where | Text | Reads as | Untranslated on |
|---|---|---|---|---|---|
| https://marvin.demarkstudio.ca/ / https://marvin.demarkstudio.ca/es/ | en/es | `section#cases > ul.case-list > li:nth-of-type(1) > p` (text) | A platform for small businesses in Canada, designed, coded, deployed and supported by me. | en 1.00 | https://marvin.demarkstudio.ca/es/ |
| https://marvin.demarkstudio.ca/ / https://marvin.demarkstudio.ca/es/ | en/es | `section#about > dl.facts > div:nth-of-type(4) > dd` (text) | Google: Foundations of Digital Marketing and E-commerce; Attract and Engage Customers w... | en 1.00 | https://marvin.demarkstudio.ca/es/ |
[... 3 more rows ...]

## Blocks in another language (16)

| Sev | Page | Where | Expected | Detected | Conf | Text |
|---|---|---|---|---|---|---|
| medium | https://marvin.demarkstudio.ca/es/ | `section#cases > ul.case-list > li:nth-of-type(1)` (text) | es | en | 1.00 | DeMark Studio: a small-business platform built and run by one developer (en inglés) |
| medium | https://marvin.demarkstudio.ca/es/ | `section#cases > ul.case-list > li:nth-of-type(1) > p` (text) | es | en | 1.00 | A platform for small businesses in Canada, designed, coded, deployed and supported by me. |
[... 7 more medium rows ...]
| low | https://marvin.demarkstudio.ca/ | `section#open-source > details.tool-group:nth-of-type(6) >...` (text) | en | es | 0.94 | canada-sales-tax Python · Decimal · 41 tests |
| low | https://marvin.demarkstudio.ca/es/ | `section#open-source > details.tool-group:nth-of-type(1) >...` (text) | es | en | 0.83 | hreflang-check Python · stdlib · 66 pruebas |
[... 5 more low rows ...]
```

After adding the product names and technical terms to [examples/allowlist.txt](examples/allowlist.txt), the same run (`--allow-file examples/allowlist.txt --format json`, [examples/report-marvin-allowlist.json](examples/report-marvin-allowlist.json)) gives `{"low": 0, "medium": 9, "high": 5}`. The 7 false positives are gone and the real English copy on `/es/` is still reported.

I then translated the four case-study titles and summaries on the Spanish home page (the case pages themselves stay in English, labelled as such), redeployed, and ran it again:

```
$ python -m untranslated_check https://marvin.demarkstudio.ca/ https://marvin.demarkstudio.ca/es/ --allow-file examples/allowlist.txt
Findings: 2 (high 1, medium 1, low 0)
medium  /es/  section#about > dl.facts > div:nth-of-type(4) > dd  es -> en 1.00
        Google: Foundations of Digital Marketing and E-commerce; Attract and Engage Customers w...
```

21 findings before, 2 after. What is left is on purpose: the certificate names are the official English course titles (the "high" finding is the same text being identical on both pages).

```
$ python -m pytest -q
...................................
35 passed in 4.38s
```

The tests run against a local EN/FR fixture site. It has one deliberately untranslated paragraph, an English `alt` on the French page, hidden and `<pre>` English text that must not be reported, and a `robots.txt` that blocks `/private/`.

## Language identification

The model in `untranslated_check/langid_model.json` combines two signals for en, fr, es, pt and de:

- the share of words that are stopwords of each language (hand-written lists);
- the average log-probability of the text's character trigrams, using profiles built by `scripts/build_langid.py` from about 42 hand-written training sentences per language.

The score grows with the number of words (up to 25), so short strings get lower confidence. Below 0.5 the answer is `unknown`. Blocks are only reported at **0.8** confidence or more (`--threshold`). By default the candidate languages are the ones the crawled site declares (`--languages site`), so an EN/FR site never gets a "German" false alarm.

Measured with `python scripts/langid_accuracy.py` on `tests/data/langid_testset.jsonl`: 225 sentences, 45 per language, written separately from the training text.

```
full sentences  225/225 = 100.0%   en 45/45  fr 45/45  es 45/45  pt 45/45  de 45/45
first 6 words   224/225 = 99.6%   en 45/45  fr 44/45  es 45/45  pt 45/45  de 45/45
first 4 words   222/225 = 98.7%   en 45/45  fr 44/45  es 43/45  pt 45/45  de 45/45
first 3 words   219/225 = 97.3%   en 45/45  fr 44/45  es 42/45  pt 44/45  de 44/45
```

Confusions: the only mistakes are on very short prefixes. Spanish is taken for Portuguese (`Por favor, recuerde`, `Nos costó tres`, confidence 0.53 to 0.56, below the reporting threshold), and French `Où as-tu mis la` reads as Spanish at 0.92. The test set is small and was written by the same author as the training sentences, so real pages score lower. The false positives above are the kind to expect: lists of names and technical words with little real text. The test suite requires at least 90% overall and 85% per language.

## CLI

```
untranslated-check URL [URL ...] [--max-pages 30] [--delay 1.0] [--no-crawl]
                   [--threshold 0.8] [--languages site|all|en,fr] [--min-words 4] [--min-chars 20]
                   [--allow TERM] [--allow-file FILE] [--no-default-allow]
                   [--format md|json] [--output FILE] [--fail-on low|medium|high|never]
untranslated-check --detect "some text"
```

Also `python -m untranslated_check`. Severities:

- **high**: text identical in two language versions (hreflang pair), or a page where most checked blocks read as another language.
- **medium**: a block in another language, confidence 0.9 or more, 6 words or more.
- **low**: other blocks in another language, and links whose `/xx/` path redirects to another language.

Exit codes, for CI:

| Code | Meaning |
|---|---|
| 0 | no finding at or above `--fail-on` (default `medium`) |
| 1 | at least one finding at or above `--fail-on` |
| 2 | usage error, unreadable allow file, or no page could be fetched |

The same text found on many pages (a footer, say) is reported once, with the list of pages in the JSON output.

## Limitations

- Five languages. Pages declared in any other language are counted and skipped.
- Plain HTTP, no JavaScript. Text that only appears after client-side rendering is not seen.
- Text split across many tiny inline elements is joined per block, but a block made only of names and numbers is too short to judge. That is by design, and it is also where the false positives come from.
- Identical-text detection only compares pages linked by `hreflang`, not pages that merely look like translations of each other.

## Author

Marvin Palencia, founder of [DeMark Studio](https://demarkstudio.ca), Miramichi, New Brunswick, Canada. Portfolio: [marvin.demarkstudio.ca](https://marvin.demarkstudio.ca)

MIT License.
