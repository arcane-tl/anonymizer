"""Detect and strip running PDF headers / footers / page marks."""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from anonymizer.models import TextBlock

_PAGE_MARK = re.compile(r"^\d+\s*\(\d+\)$")
_DOC_STAMP = re.compile(r"(?i)^doc\s+\d+")
_LEGAL_FORM = re.compile(
    r"(?i)\b(oyj|oy|abp|ab|ltd|limited|inc|corp|llc|gmbh|plc)\b"
)

# Short form-field footers repeated on every page
_CHROME_FIELD = re.compile(
    r"(?i)^\s*("
    r"sopimusnumero|luottopäätösnumero|luottopaatosnumero|"
    r"y-tunnus|alv-numero|alv\s*numero|"
    r"puh\.?|puhelin|phone|tel\.?"
    r")\b"
)
_ONLY_URLS = re.compile(
    r"(?i)^(?:\s*(?:https?://|www\.)\S+\s*)+$"
)
_ONLY_PHONE = re.compile(
    r"(?i)^(?:puh\.?|puhelin|phone|tel\.?)?\s*[:：]?\s*"
    r"[\d\s\-./()+]+\s*$"
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _looks_like_letterhead(text: str) -> bool:
    """Org + address-ish one-liner repeated as page chrome."""
    t = text.strip()
    if len(t) < 20 or len(t) > 200:
        return False
    if not _LEGAL_FORM.search(t):
        return False
    if re.search(r"\d{5}", t) or re.search(r"(?i)https?://|www\.", t):
        return True
    if re.search(
        r"(?i)(katu|tie|kuja|road|street|raitti|väylä)\b", t
    ):
        return True
    return False


def _looks_like_page_chrome(text: str) -> bool:
    """Contract no., Y-tunnus/ALV, bare URL lines, bare phone — footer chrome."""
    t = text.strip()
    if not t or len(t) > 220:
        return False
    if _PAGE_MARK.match(t) or _DOC_STAMP.match(t):
        return True
    if _looks_like_letterhead(t):
        return True
    # Multi-line form: Sopimusnumero / Luottopäätösnumero block
    if _CHROME_FIELD.search(t):
        # Entire block is only those fields + short numbers (no long prose)
        if len(t) <= 180 and not re.search(r"[.!]{1}.{40,}", t):
            return True
    if _ONLY_URLS.match(t):
        return True
    if _ONLY_PHONE.match(t) and len(t) < 40:
        return True
    # "Y-tunnus: … ALV-numero: …" alone
    if re.search(r"(?i)y-tunnus", t) and re.search(r"(?i)alv", t) and len(t) < 120:
        return True
    return False


def filter_running_headers(
    blocks: list[TextBlock],
    *,
    keep_headers: bool = False,
) -> list[TextBlock]:
    """Drop page marks, doc stamps, letterheads, and repeated footer chrome."""
    if keep_headers or not blocks:
        return blocks

    norms = [_norm(b.text) for b in blocks]
    counts = Counter(n for n in norms if n)

    # Pages each normalized text appears on (multi-page = running header/footer)
    pages_for: dict[str, set[int]] = defaultdict(set)
    for b in blocks:
        n = _norm(b.text)
        if b.page is not None:
            pages_for[n].add(b.page)
        else:
            # No page index: fall back to occurrence count via unique placeholders
            pages_for[n].add(len(pages_for[n]))

    drop_norms: set[str] = set()

    for n, c in counts.items():
        if not n:
            continue
        sample = next(b.text for b in blocks if _norm(b.text) == n)
        n_pages = len(pages_for.get(n, set()))

        # Always drop pure page chrome regardless of count
        if _PAGE_MARK.match(sample.strip()) or _DOC_STAMP.match(sample.strip()):
            drop_norms.add(n)
            continue

        # Letterhead or field chrome repeated across pages / many times
        chrome = _looks_like_page_chrome(sample)
        if chrome and (n_pages >= 2 or c >= 2):
            drop_norms.add(n)
            continue

        # Any short exact text on ≥3 pages → running header/footer
        if n_pages >= 3 and len(sample) <= 200:
            drop_norms.add(n)
            continue

    kept: list[TextBlock] = []
    for b in blocks:
        t = b.text.strip()
        if not t:
            kept.append(b)
            continue
        if _norm(t) in drop_norms:
            continue
        if _PAGE_MARK.match(t) or _DOC_STAMP.match(t):
            continue
        kept.append(b)
    return kept
