"""Best-effort PDF block kind classification for Markdown / Text PDF.

Uses font size (relative to page median), bold flags, and list markers.
Prefers under-calling headings over promoting body paragraphs.
"""

from __future__ import annotations

import re
import statistics

from anonymizer.models import BlockKind

# Unicode bullets + common markdown / Word list prefixes
_LIST_START = re.compile(
    r"^(?:"
    r"[•●○▪▸►·]\s+"
    r"|[-*+]\s+"
    r"|\d{1,3}[.)]\s+"
    r"|[A-Za-z][.)]\s+"
    r")"
)

# ALL-CAPS / shouty section labels (same spirit as extract/pdf._is_section_header)
_SECTION_HEADER = re.compile(
    r"^[A-ZÅÄÖ0-9][A-ZÅÄÖ0-9\s/.\-]{0,48}$",
    re.UNICODE,
)


def looks_like_list_item(text: str) -> bool:
    first = text.strip().split("\n", 1)[0].strip()
    return bool(_LIST_START.match(first))


def _is_shouty_header(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 50:
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 2:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= 0.85 and bool(_SECTION_HEADER.match(s))


def heading_level_for_size(size: float, page_median_size: float) -> int | None:
    """Map font size vs page median to heading level 1–3, or None."""
    median = page_median_size if page_median_size > 0 else 11.0
    ratio = size / median
    if ratio >= 1.55:
        return 1
    if ratio >= 1.30:
        return 2
    if ratio >= 1.15:
        return 3
    return None


def page_median_font_size(sizes: list[float]) -> float:
    positive = [s for s in sizes if s > 0]
    if not positive:
        return 11.0
    return float(statistics.median(positive))


def block_font_stats(pymupdf_block: dict) -> tuple[float, bool]:
    """Return (max_span_size, mostly_bold) for a pymupdf text dict block."""
    max_size = 0.0
    bold_chars = 0
    total_chars = 0
    for line in pymupdf_block.get("lines", []) or []:
        for span in line.get("spans", []) or []:
            text = span.get("text") or ""
            if not text.strip():
                continue
            size = float(span.get("size") or 0.0)
            if size > max_size:
                max_size = size
            n = len(text)
            total_chars += n
            flags = int(span.get("flags") or 0)
            font = (span.get("font") or "").lower()
            # MuPDF: bit 4 = bold
            if (flags & 16) or ("bold" in font):
                bold_chars += n
    bold = total_chars > 0 and (bold_chars / total_chars) >= 0.5
    return max_size, bold


def classify_pdf_block(
    text: str,
    *,
    max_size: float,
    page_median_size: float,
    bold: bool = False,
) -> tuple[BlockKind, int | None]:
    """Classify extracted PDF text into heading / list / paragraph."""
    stripped = text.strip()
    if not stripped:
        return BlockKind.PARAGRAPH, None

    if looks_like_list_item(stripped):
        return BlockKind.LIST_ITEM, None

    first = stripped.split("\n", 1)[0].strip()
    words = first.split()
    word_count = len(words)
    char_count = len(first)
    is_short = char_count <= 80 and word_count <= 14

    # Long multi-line body blocks: do not promote
    if len(stripped) > 140 and stripped.count(" ") > 24:
        return BlockKind.PARAGRAPH, None
    if stripped.count("\n") >= 3 and len(stripped) > 100:
        return BlockKind.PARAGRAPH, None

    level = heading_level_for_size(max_size, page_median_size)
    if level is not None and is_short:
        return BlockKind.HEADING, level

    # Bold short line near body size → modest heading
    if (
        bold
        and is_short
        and word_count <= 10
        and char_count <= 60
        and max_size >= page_median_size * 0.98
    ):
        return BlockKind.HEADING, 3

    if is_short and word_count <= 8 and _is_shouty_header(first):
        return BlockKind.HEADING, 2

    return BlockKind.PARAGRAPH, None
