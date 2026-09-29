from untranslated_check.extract import parse_page, parse_tree, selector

HTML = """<!doctype html><html lang="fr"><head><title>Le titre</title>
<meta name="description" content="Une description de la page">
<link rel="alternate" hreflang="en" href="/en/page">
<link rel="alternate" hreflang="fr" href="https://example.com/fr/page#top">
<script>var english = "should not appear";</script></head>
<body>
<div id="app"><section class="hero big"><h1>Bonjour <em>tout</em> le monde</h1>
<p>Premier paragraphe avec un <a href="/lien">lien en ligne</a> dedans.
<p>Second paragraphe sans balise fermante
</section>
<ul><li>Un<li>Deux<li lang="en">Three items</ul>
<nav><a href="/a">Accueil</a><a href="/b#frag">Services</a></nav>
<img src="x.png" alt="Texte alternatif">
<button aria-label="Fermer la fenetre">X</button>
<input placeholder="Votre nom">
<span title="Info bulle">i</span>
<pre>code block text</pre><code>inline code</code><noscript>no script</noscript>
<div hidden>cache</div><div aria-hidden="true">aussi cache</div>
<div style="display:none">invisible</div><p translate="no">Ne pas traduire</p>
<p class="notranslate">Pas non plus</p>
</div></body></html>"""


def blocks(page, kind="text"):
    return {b.text: b for b in page.blocks if b.kind == kind}


def test_head_metadata_and_alternates():
    page = parse_page(HTML, "https://example.com/fr/page")
    assert page.lang == "fr"
    assert page.title == "Le titre"
    assert page.alternates == {"en": "https://example.com/en/page", "fr": "https://example.com/fr/page"}
    assert "https://example.com/b" in page.links
    assert blocks(page, "meta:description")["Une description de la page"].selector == 'meta[name="description"]'
    assert blocks(page, "head:title")["Le titre"].selector == "head > title"


def test_text_blocks_and_selectors():
    page = parse_page(HTML, "https://example.com/fr/page")
    text = blocks(page)
    assert text["Bonjour tout le monde"].selector == "div#app > section.hero > h1"
    # inline link text stays inside the paragraph
    assert "Premier paragraphe avec un lien en ligne dedans." in text
    assert "lien en ligne" not in text
    # unclosed <p> and <li> are closed implicitly
    assert text["Second paragraphe sans balise fermante"].selector == "div#app > section.hero > p:nth-of-type(2)"
    assert text["Deux"].selector == "div#app > ul > li:nth-of-type(2)"
    # links outside a text block are their own blocks
    assert text["Accueil"].selector == "div#app > nav > a:nth-of-type(1)"
    # lang attribute on the element wins over the page language
    assert text["Three items"].lang == "en"
    assert text["Deux"].lang == "fr"


def test_attributes_are_collected():
    page = parse_page(HTML, "https://example.com/fr/page")
    assert blocks(page, "attr:alt")["Texte alternatif"].selector == "div#app > img"
    assert "Fermer la fenetre" in blocks(page, "attr:aria-label")
    assert "Votre nom" in blocks(page, "attr:placeholder")
    assert "Info bulle" in blocks(page, "attr:title")


def test_excluded_content():
    page = parse_page(HTML, "https://example.com/fr/page")
    all_text = " ".join(b.text for b in page.blocks)
    for hidden in ("should not appear", "code block text", "inline code", "no script", "cache",
                   "invisible", "Ne pas traduire", "Pas non plus"):
        assert hidden not in all_text


def test_selector_without_id():
    root = parse_tree("<html><body><main><p>a</p><div class='x:y card'><p>b</p></div></main></body></html>")
    p = root.elements()[0].elements()[0].elements()[0].elements()[1].elements()[0]
    assert selector(p) == "body > main > div.card > p"
