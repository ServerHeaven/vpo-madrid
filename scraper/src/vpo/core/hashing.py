"""Hashes of raw bytes, normalized text and relevant HTML fragments (ARCHITECTURE 3.4)."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from selectolax.lexbor import LexborHTMLParser

# Zero width space / non-joiner / joiner, word joiner, BOM, soft hyphen, Mongolian vowel separator.
_ZERO_WIDTH = dict.fromkeys((0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x180E))

_SKIPPED_TAGS = frozenset({"script", "style", "noscript", "template", "-comment"})

# Deliberately narrow: it must match a whole text node, so sentences that merely contain a date
# ("podrá ser consultado el ...") are never dropped.
_VISIT_NOISE = re.compile(
    r"(?:(?:página )?(?:consultad|visitad)[oa](?: por última vez)? el|fecha de consulta|última visita)"
    r" ?:? ?\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"
    r"(?:,? (?:a las )?\d{1,2}:\d{2}(?::\d{2})?(?: ?h(?:oras)?)?)?\.?",
    re.IGNORECASE,
)

# Session ids and Cloudflare's e-mail obfuscation change on every request.
_SESSION_ID = re.compile(r";jsessionid=[^?#]*", re.IGNORECASE)
_CF_EMAIL = "/cdn-cgi/l/email-protection"


class SelectorNotFound(ValueError):
    """The CSS selector matches nothing in the page."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> str:
    """NFKC, without zero-width characters, with whitespace runs collapsed to one space."""
    return " ".join(unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH).split())


def sha256_text(text: str) -> str:
    """Hash of normalize_text(text)."""
    return sha256_bytes(normalize_text(text).encode("utf-8", errors="surrogatepass"))


def _stable_href(href: str) -> str:
    href = href.strip()
    if _CF_EMAIL in href:
        return href.partition("#")[0]
    return _SESSION_ID.sub("", href)


def html_fragment_text(html: str, selector: str) -> str:
    """Stable text of every node matching ``selector``, including link targets.

    Nodes come in document order and each one only once, even if the selector matches it
    several times or also matches one of its ancestors.
    """
    tree = LexborHTMLParser(html)
    matched = {node.mem_id for node in tree.css(selector)}
    pieces: list[str] = []
    found = False

    # Explicit stack: badly nested pages could exceed the recursion limit.
    stack = [(tree.root, False)] if matched and tree.root is not None else []
    while stack:
        node, inside = stack.pop()
        tag = node.tag
        if tag in _SKIPPED_TAGS:
            continue
        if node.mem_id in matched:
            inside = found = True
        if inside:
            if tag == "-text":
                text = normalize_text(node.text_content or "")
                if text and not _VISIT_NOISE.fullmatch(text):
                    pieces.append(text)
                continue
            if tag in ("a", "area"):
                href = _stable_href(node.attributes.get("href") or "")
                if href:
                    pieces.append(f"<{href}>")
        children = []
        child = node.child
        while child is not None:
            children.append((child, inside))
            child = child.next
        stack.extend(reversed(children))

    if not found:
        raise SelectorNotFound(f"El selector «{selector}» no coincide con ningún nodo de la página")
    return normalize_text(" ".join(pieces))


def sha256_fragment(html: str, selector: str) -> str:
    return sha256_text(html_fragment_text(html, selector))
