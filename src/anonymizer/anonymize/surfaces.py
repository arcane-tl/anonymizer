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


def _email_wrap_variants(text: str) -> list[str]:
    """PDF line-break forms of email addresses (TLD / domain / @ splits)."""
    if "@" not in text or "." not in text:
        return []
    out: list[str] = []
    # user@\nexample.com
    at = text.find("@")
    if at > 0:
        out.append(text[: at + 1] + "\n" + text[at + 1 :])
    # user@exam\nple.com — split once in the domain label before the last dot
    local, _, domain = text.partition("@")
    if domain and "." in domain:
        host, dot, tld = domain.rpartition(".")
        if host and tld:
            # Mid-host wrap: exam\nple.com
            if len(host) >= 4:
                mid = max(2, len(host) // 2)
                out.append(f"{local}@{host[:mid]}\n{host[mid:]}{dot}{tld}")
            # TLD wrap: bestcaravan.f\ni  (common PDF soft-wrap)
            if len(tld) >= 2:
                out.append(f"{local}@{host}{dot}{tld[0]}\n{tld[1:]}")
                out.append(f"{local}@{host}{dot}{tld[:-1]}\n{tld[-1]}")
            # Truncated visible form (search still blacks the visible fragment)
            if len(tld) >= 2:
                out.append(f"{local}@{host}{dot}{tld[0]}")
    # local\n@domain
    if local and len(local) >= 3:
        out.append(f"{local}\n@{domain}")
    return out


def surface_search_variants(text: str) -> list[str]:
    """Variants worth searching in PDF/DOCX layout.

    Covers NBSP↔space, soft-hyphen / zero-width stripping, hyphenated line
    breaks (``Foo-\\nBar``), soft-wrap newlines at spaces, dehyphenated
    compounds (``FooBar`` from ``Foo-Bar``), and email PDF wraps
    (``user@domain.f\\ni``).
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

    for v in _email_wrap_variants(stripped):
        add(v)
    if collapsed != stripped:
        for v in _email_wrap_variants(collapsed):
            add(v)

    for v in _url_wrap_variants(stripped):
        add(v)

    return variants


def _url_wrap_variants(text: str) -> list[str]:
    """PDF soft-wrap forms of http(s) URLs (hyphen+newline mid-path)."""
    low = text.casefold()
    if not (low.startswith("http://") or low.startswith("https://") or low.startswith("www.")):
        return []
    out: list[str] = []
    # Trailing punctuation often glued in PDF extract
    for trimmed in (text, text.rstrip(".,;:!?)\"'")):
        if trimmed and trimmed != text:
            out.append(trimmed)
    # Soft hyphen wraps in long paths: Continuous-\nimprovement.aspx
    if "-" in text:
        out.append(text.replace("-", "-\n"))
        # Also split before a late path segment
        for sep in ("/", "-", "_"):
            idx = text.rfind(sep, 0, max(len(text) - 8, 1))
            if idx > 20:
                out.append(text[:idx] + "\n" + text[idx:])
                out.append(text[: idx + 1] + "\n" + text[idx + 1 :])
    return out


def surface_appears_in_text(haystack: str, clear: str) -> bool:
    """True if *clear* (or a search variant) remains in extracted *haystack*."""
    if not clear or not haystack:
        return False
    # Also check repair-joined haystack so PDF ``.f\\ni`` residuals match ``.fi``
    try:
        from anonymizer.extract.text_repair import repair_text_artifacts

        corpora = (haystack, repair_text_artifacts(haystack))
    except Exception:  # noqa: BLE001
        corpora = (haystack,)
    for corpus in corpora:
        for variant in surface_search_variants(clear):
            if variant in corpus:
                return True
        norm_h = " ".join(corpus.split())
        if not norm_h:
            continue
        for variant in surface_search_variants(clear):
            norm_v = " ".join(variant.split())
            if norm_v and norm_v in norm_h:
                return True
    return False
