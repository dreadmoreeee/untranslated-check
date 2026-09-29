"""Decide which text blocks are worth checking, and strip what should never be judged."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .langid import words

# Names that read the same in every language. Extend with --allow / --allow-file.
DEFAULT_ALLOW = [
    "DeMark Studio", "DeMark", "Miramichi", "New Brunswick", "Nouveau-Brunswick", "Canada",
    "Marvin Palencia", "Moncton", "Fredericton", "Saint John", "Halifax", "Stripe", "WordPress",
    "Shopify", "WooCommerce", "Google", "Google Maps", "GitHub", "Python", "JavaScript",
    "TypeScript", "Next.js", "React", "LinkedIn", "Facebook", "Instagram", "WhatsApp", "YouTube",
]

_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_HAS_DIGIT = re.compile(r"\d")
_CURRENCY = re.compile(r"[$\u20ac\u00a3\u00a5\u00a2%#]")
_CODE_CHARS = re.compile(r"[_{}<>=;\[\]\\|`^~]|\(\)|::|=>|->|/")
_CAMEL = re.compile(r"^[a-z]+[A-Z][A-Za-z]*$")
_DOTTED = re.compile(r"^\w+\.\w+", re.U)
_PUNCT_EDGE = re.compile(r"^[\W_]+|[\W_]+$", re.U)
_SPACE = re.compile(r"\s+")


def load_allow_file(path: str) -> list[str]:
    """One term per line; blank lines and lines starting with # are ignored."""
    terms = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                terms.append(line)
    return terms


def _allow_regex(terms: list[str]) -> re.Pattern | None:
    terms = sorted({t.strip() for t in terms if t.strip()}, key=len, reverse=True)
    if not terms:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t) for t in terms) + r")(?!\w)", re.I)


def _code_like(token: str) -> bool:
    core = _PUNCT_EDGE.sub("", token)
    if not core:  # operators such as "=" or "=>"
        return bool(_CODE_CHARS.search(token))
    return bool(_CODE_CHARS.search(core) or _CAMEL.match(core) or (_DOTTED.match(core) and not core.endswith(".")))


def normalize(text: str) -> str:
    """Form used to compare blocks across pages: NFC, lower case, single spaces, plain quotes."""
    text = unicodedata.normalize("NFC", text).lower()
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u00a0", " ")
    return _PUNCT_EDGE.sub("", _SPACE.sub(" ", text).strip())


@dataclass
class FilterResult:
    keep: bool
    text: str      # text left after removing allowlisted names, URLs, emails, numbers and code
    reason: str    # "", "code", "short"
    words: int


class TextFilter:
    def __init__(self, allow: list[str] | None = None, min_words: int = 4, min_chars: int = 20) -> None:
        self.allow = list(allow or [])
        self.min_words = min_words
        self.min_chars = min_chars
        self._allow_re = _allow_regex(self.allow)

    def strip(self, text: str) -> str:
        text = unicodedata.normalize("NFC", text)
        text = _URL.sub(" ", text)
        text = _EMAIL.sub(" ", text)
        if self._allow_re is not None:
            text = self._allow_re.sub(" ", text)
        kept = [t for t in text.split()
                if not _HAS_DIGIT.search(t) and not _CURRENCY.search(t) and not _code_like(t)]
        return " ".join(kept)

    def check(self, text: str) -> FilterResult:
        tokens = text.split()
        if tokens and sum(_code_like(t) for t in tokens) / len(tokens) > 0.3:
            return FilterResult(False, "", "code", 0)
        cleaned = self.strip(text)
        n = len(words(cleaned))
        if n < self.min_words or len(cleaned) < self.min_chars:
            return FilterResult(False, cleaned, "short", n)
        return FilterResult(True, cleaned, "", n)
