"""Collect cleartext surfaces to remove from native PDF/DOCX output."""

from __future__ import annotations

from dataclasses import dataclass


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


def surface_search_variants(text: str) -> list[str]:
    """Variants worth searching in layout (NBSP / whitespace normalize)."""
    variants: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        if s and s not in seen:
            seen.add(s)
            variants.append(s)

    add(text)
    if "\u00a0" in text:
        add(text.replace("\u00a0", " "))
    if " " in text:
        add(text.replace(" ", "\u00a0"))
    collapsed = " ".join(text.split())
    add(collapsed)
    return variants
