"""Collect cleartext surfaces to remove from native PDF/DOCX output."""

from __future__ import annotations

from dataclasses import dataclass

# Soft hyphen and other invisible format chars often present in PDF text layers.
_INVISIBLE_CHARS = (
    "\u00ad",  # soft hyphen
    "\u200b",  # zero-width space
    "\u200c",  # ZWNJ
    "\u200d",  # ZWJ
    "\ufeff",  # BOM / ZWNBSP
)


@dataclass(frozen=True)
class RedactSurface:
    """One unique cleartext string and its Markdown-side replacement tag."""

    clear: str
    placeholder: str  # e.g. [PERSON_1]


def surfaces_from_mapping(mapping: dict[str, str]) -> list[RedactSurface]:
    """Build unique surfaces from placeholder→original map.

    Longest cleartext first so multi-word ORGs are applied before substrings.
    Empty / whitespace-only originals are dropped.
    """
    seen: set[str] = set()
    items: list[RedactSurface] = []
    for placeholder, original in mapping.items():
        clear = (original or "").strip()
        if not clear or clear in seen:
            continue
        seen.add(clear)
        items.append(RedactSurface(clear=clear, placeholder=placeholder))
    items.sort(key=lambda s: (-len(s.clear), s.clear.casefold()))
    return items


def _strip_invisible(text: str) -> str:
    out = text
    for ch in _INVISIBLE_CHARS:
        if ch in out:
            out = out.replace(ch, "")
    return out


def surface_search_variants(text: str) -> list[str]:
    """Variants worth searching in PDF/DOCX layout.

    Covers NBSP↔space, soft-hyphen / zero-width stripping, hyphenated line
    breaks (``Foo-\\nBar``), soft-wrap newlines at spaces, and dehyphenated
    compounds (``FooBar`` from ``Foo-Bar``).
    """
    variants: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        if s and s not in seen:
            seen.add(s)
            variants.append(s)

    add(text)

    stripped = _strip_invisible(text)
    add(stripped)
    if "\u00ad" in text:
        add(text.replace("\u00ad", "-"))
        add(text.replace("\u00ad", "-\n"))
        add(text.replace("\u00ad", ""))

    if "\u00a0" in text:
        add(text.replace("\u00a0", " "))
    if " " in text:
        add(text.replace(" ", "\u00a0"))

    collapsed = " ".join(stripped.split())
    add(collapsed)

    # Soft-wrap at spaces (PDF line breaks often become \\n in the text layer)
    if " " in collapsed:
        add(collapsed.replace(" ", "\n"))

    # Hyphenated line break + dehyphenated compound
    for base in (text, stripped, collapsed):
        if "-" not in base:
            continue
        add(base.replace("-", "-\n"))
        add(base.replace("-", ""))
        add(base.replace("-", "\u00ad"))

    return variants


def surface_appears_in_text(haystack: str, clear: str) -> bool:
    """True if *clear* (or a search variant) remains in extracted *haystack*."""
    if not clear or not haystack:
        return False
    for variant in surface_search_variants(clear):
        if variant in haystack:
            return True
    # Whitespace-normalized fallback (covers NBSP / multi-space / newlines)
    norm_h = " ".join(haystack.split())
    if not norm_h:
        return False
    for variant in surface_search_variants(clear):
        norm_v = " ".join(variant.split())
        if norm_v and norm_v in norm_h:
            return True
    return False
