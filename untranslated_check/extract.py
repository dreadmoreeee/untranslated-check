"""Parse HTML into a small tree and pull out the visible text blocks with CSS selectors."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urldefrag

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
        "source", "track", "wbr"}
# Never read text from these (or from anything inside them).
SKIP = {"script", "style", "noscript", "code", "pre", "template", "svg", "math", "iframe",
        "object", "canvas", "kbd", "samp", "var", "head", "textarea", "select"}
# Phrasing elements: their text belongs to the nearest enclosing block.
INLINE = {"span", "strong", "em", "b", "i", "u", "s", "small", "mark", "abbr", "time", "sup",
          "sub", "q", "cite", "del", "ins", "font", "bdi", "bdo", "data", "br", "wbr", "img",
          "picture"}
# Elements whose text is a unit of copy; links inside them are inline.
TEXT_BLOCKS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "button", "label", "td", "th",
               "dt", "dd", "figcaption", "blockquote", "summary", "legend", "caption", "option"}
BLOCK_STARTS = {"p", "div", "ul", "ol", "dl", "table", "section", "article", "header", "footer",
                "main", "nav", "aside", "form", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
                "figure", "hr", "pre", "address", "fieldset", "details"}
TEXT_ATTRS = ("alt", "title", "aria-label", "placeholder")

_IDENT = re.compile(r"^-?[A-Za-z_][A-Za-z0-9_-]*$")
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
_SPACE = re.compile(r"\s+")


class Node:
    __slots__ = ("tag", "attrs", "parent", "children")

    def __init__(self, tag: str, attrs: dict[str, str], parent: "Node | None") -> None:
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.children: list[Node | str] = []

    def elements(self) -> list["Node"]:
        return [c for c in self.children if isinstance(c, Node)]


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.stack = [self.root]

    def _close_to(self, tags: set[str], boundary: set[str]) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            tag = self.stack[i].tag
            if tag in tags:
                del self.stack[i:]
                return
            if tag in boundary:
                return

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK_STARTS:
            self._close_to({"p"}, {"button", "td", "th", "li", "div", "section", "article", "body"})
        if tag == "li":
            self._close_to({"li"}, {"ul", "ol", "menu"})
        elif tag in ("dt", "dd"):
            self._close_to({"dt", "dd"}, {"dl"})
        elif tag == "tr":
            self._close_to({"tr"}, {"table", "thead", "tbody", "tfoot"})
        elif tag in ("td", "th"):
            self._close_to({"td", "th"}, {"tr", "table"})
        elif tag == "option":
            self._close_to({"option"}, {"select", "datalist"})
        node = Node(tag, {k.lower(): (v or "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, {k.lower(): (v or "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_tree(html: str) -> Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


def selector(node: Node) -> str:
    """A CSS selector for ``node``: tag, first class, :nth-of-type; stops at an id or <body>."""
    parts = []
    n: Node | None = node
    while n is not None and n.tag != "#root":
        ident = n.attrs.get("id", "")
        if ident and _IDENT.match(ident):
            parts.append(f"{n.tag}#{ident}")
            break
        part = n.tag
        for cls in n.attrs.get("class", "").split():
            if _IDENT.match(cls):
                part += "." + cls
                break
        if n.parent is not None:
            same = [c for c in n.parent.elements() if c.tag == n.tag]
            if len(same) > 1:
                part += f":nth-of-type({same.index(n) + 1})"
        parts.append(part)
        if n.tag in ("body", "head", "html"):
            break
        n = n.parent
    return " > ".join(reversed(parts))


def _excluded(node: Node) -> bool:
    a = node.attrs
    if "hidden" in a or a.get("aria-hidden", "").lower() == "true":
        return True
    if _HIDDEN_STYLE.search(a.get("style", "")):
        return True
    if node.tag == "input" and a.get("type", "").lower() == "hidden":
        return True
    # Content explicitly marked as not to be translated.
    if a.get("translate", "").lower() == "no" or "notranslate" in a.get("class", "").split():
        return True
    return False


def clean_text(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


@dataclass
class Block:
    selector: str
    kind: str        # text, attr:alt, attr:title, attr:aria-label, attr:placeholder, head:title, meta:description
    text: str
    lang: str | None  # nearest lang attribute on the element or an ancestor


@dataclass
class ParsedPage:
    lang: str | None = None
    alternates: dict[str, str] = field(default_factory=dict)   # hreflang -> absolute URL
    links: list[str] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    title: str = ""


def _lang_of(node: Node) -> str | None:
    n: Node | None = node
    while n is not None:
        value = n.attrs.get("lang") or n.attrs.get("xml:lang")
        if value:
            return value.strip()
        n = n.parent
    return None


def parse_page(html: str, base_url: str) -> ParsedPage:
    root = parse_tree(html)
    page = ParsedPage()
    base = base_url

    # Pass 1: head metadata, links and the base URL (anywhere in the document).
    def meta_walk(node: Node) -> None:
        nonlocal base
        for c in node.elements():
            a = c.attrs
            if c.tag == "html" and a.get("lang") and page.lang is None:
                page.lang = a["lang"].strip()
            elif c.tag == "base" and a.get("href"):
                base = urljoin(base_url, a["href"])
            elif c.tag == "link" and "alternate" in a.get("rel", "").lower().split() and a.get("hreflang") and a.get("href"):
                page.alternates.setdefault(a["hreflang"].strip().lower(), a["href"])
            elif c.tag == "title" and node.tag == "head" and not page.title:
                page.title = clean_text("".join(x for x in c.children if isinstance(x, str)))
                if page.title:
                    page.blocks.append(Block("head > title", "head:title", page.title, _lang_of(c)))
            elif c.tag == "meta" and a.get("name", "").lower() == "description" and a.get("content", "").strip():
                page.blocks.append(Block('meta[name="description"]', "meta:description",
                                         clean_text(a["content"]), _lang_of(c)))
            elif c.tag == "a" and a.get("href"):
                page.links.append(a["href"])
            meta_walk(c)

    meta_walk(root)
    page.alternates = {k: urldefrag(urljoin(base, v))[0] for k, v in page.alternates.items()}
    page.links = [urldefrag(urljoin(base, h.strip()))[0] for h in page.links]

    # Pass 2: visible text grouped by owning block, plus text attributes.
    owners: list[Node] = []
    texts: dict[int, list[str]] = {}

    def walk(node: Node, owner: Node) -> None:
        for c in node.children:
            if isinstance(c, str):
                if owner.tag != "#root":
                    if id(owner) not in texts:
                        owners.append(owner)
                        texts[id(owner)] = []
                    texts[id(owner)].append(c)
                continue
            if c.tag in SKIP or _excluded(c):
                continue
            for attr in TEXT_ATTRS:
                value = clean_text(c.attrs.get(attr, ""))
                if value:
                    page.blocks.append(Block(selector(c), f"attr:{attr}", value, _lang_of(c)))
            if c.tag == "br":
                if id(owner) in texts:
                    texts[id(owner)].append(" ")
                continue
            if c.tag in INLINE:
                child_owner = owner
            elif c.tag == "a" and owner.tag in TEXT_BLOCKS:
                child_owner = owner
            else:
                child_owner = c
            walk(c, child_owner)

    walk(root, root)
    for node in owners:
        text = clean_text("".join(texts[id(node)]))
        if text and node.tag not in ("html", "#root"):
            page.blocks.append(Block(selector(node), "text", text, _lang_of(node)))
    return page
