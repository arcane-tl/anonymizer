"""PDF extraction with optional OCR and soft-wrap reflow."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from anonymizer.anonymize.language import tesseract_lang_string
from anonymizer.extract.ocr import ocr_pdf_to_searchable
from anonymizer.extract.text_repair import repair_text_artifacts
from anonymizer.models import BlockKind, ExtractedDoc, TextBlock

logger = logging.getLogger(__name__)

# Heuristic: average chars per page below this → try OCR
THIN_TEXT_CHARS_PER_PAGE = 40

_LABEL_END = re.compile(r"[:：]\s*$")
# Short shouty headers: ASIAKAS, MYYJÄLIIKE, LEASINGKOHDE
_SECTION_HEADER = re.compile(
    r"^[A-ZÅÄÖ0-9][A-ZÅÄÖ0-9\s/.\-]{0,48}$",
    re.UNICODE,
)


def _is_section_header(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 50:
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 2:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= 0.85


def _looks_like_label_line(line: str) -> bool:
    """Form labels are short lines ending with ':' (e.g. Osoite:, Y-tunnus:)."""
    s = line.strip()
    if not s:
        return False
    # Multi-line labels ending mid-phrase with /
    if s.endswith("/") and len(s) < 80 and len(s.split()) <= 12:
        # Body wrap rarely ends with /; keep short slash-labels
        if s[0].islower():
            return False
        return True
    if not _LABEL_END.search(s):
        return False
    # Body soft-wraps often continue with lowercase; form labels start capitalised
    if s[0].islower():
        return False
    # Long body sentences can end with ':' — not form labels
    if len(s) > 55 or len(s.split()) > 6:
        return False
    return True


def _join_pdf_lines(lines: list[str]) -> str:
    """Join visual PDF lines: reflow body soft-wraps; keep form structure.

    Keep newline when previous line is a form label (ends with ':') or a short
    section header. Soft-hyphen wraps become compounds (ETA-\\nmaat → ETA-maat).
    Other mid-sentence wraps become a single space.
    """
    cleaned = [ln.strip() for ln in lines if ln and ln.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]

    parts: list[str] = [cleaned[0]]
    for nxt in cleaned[1:]:
        prev = parts[-1]
        # Structural break: form label → value
        if _looks_like_label_line(prev):
            parts.append("\n")
            parts.append(nxt)
            continue
        # Section header standing alone
        if _is_section_header(prev) and len(prev) <= 50:
            parts.append("\n")
            parts.append(nxt)
            continue
        # Next line is itself a new label / header
        if _looks_like_label_line(nxt) or (
            _is_section_header(nxt) and len(nxt) <= 40
        ):
            parts.append("\n")
            parts.append(nxt)
            continue

        # Soft hyphenation at end of line
        if prev.endswith("-") and nxt and nxt[0].isalpha():
            parts[-1] = prev + nxt  # keep hyphen: ETA- + maat
            continue

        # Default body soft-wrap → space
        parts.append(" ")
        parts.append(nxt)

    return "".join(parts)


def _extract_with_pymupdf(path: Path) -> tuple[list[TextBlock], int, int]:
    import pymupdf as fitz

    doc = fitz.open(path)
    blocks: list[TextBlock] = []
    total_chars = 0
    try:
        for page_i, page in enumerate(doc, start=1):
            # "blocks" mode: list of (x0,y0,x1,y1, text, block_no, block_type)
            page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            page_blocks = 0
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:  # text
                    continue
                lines: list[str] = []
                for line in block.get("lines", []):
                    spans = [s.get("text", "") for s in line.get("spans", [])]
                    line_text = "".join(spans).strip()
                    if line_text:
                        lines.append(line_text)
                para = repair_text_artifacts(_join_pdf_lines(lines))
                if para:
                    total_chars += len(para)
                    page_blocks += 1
                    blocks.append(
                        TextBlock(text=para, kind=BlockKind.PARAGRAPH, page=page_i)
                    )
            # Fallback if dict empty
            if page_blocks == 0:
                plain = page.get_text("text").strip()
                if plain:
                    # Reflow crude text fallback by line
                    raw_lines = [ln.strip() for ln in plain.splitlines() if ln.strip()]
                    para = repair_text_artifacts(_join_pdf_lines(raw_lines))
                    if para:
                        total_chars += len(para)
                        blocks.append(
                            TextBlock(
                                text=para, kind=BlockKind.PARAGRAPH, page=page_i
                            )
                        )
        return blocks, doc.page_count, total_chars
    finally:
        doc.close()


def is_thin_text(page_count: int, total_chars: int) -> bool:
    if page_count <= 0:
        return True
    return (total_chars / page_count) < THIN_TEXT_CHARS_PER_PAGE


def extract_pdf(
    path: Path,
    *,
    force_ocr: bool = False,
    no_ocr: bool = False,
    lang_flag: str = "auto",
    keep_headers: bool = False,
    progress=None,  # Callable[[str], None] | None
) -> ExtractedDoc:
    from anonymizer.extract.headers import filter_running_headers

    def _p(msg: str) -> None:
        if progress:
            progress(msg)

    _p("Reading PDF text layer…")
    blocks, page_count, total_chars = _extract_with_pymupdf(path)
    used_ocr = False

    need_ocr = force_ocr or (not no_ocr and is_thin_text(page_count, total_chars))
    if need_ocr and not no_ocr:
        tess_lang = tesseract_lang_string(lang_flag)
        reason = "forced" if force_ocr else "thin text layer"
        _p(f"Running OCR ({reason}; langs={tess_lang})…")
        logger.info("Running OCR on %s (langs=%s)", path, tess_lang)
        ocr_path = None
        try:
            ocr_path = ocr_pdf_to_searchable(path, tesseract_langs=tess_lang)
            _p("Re-extracting text from OCR result…")
            blocks, page_count, total_chars = _extract_with_pymupdf(ocr_path)
            used_ocr = True
        except RuntimeError as exc:
            if force_ocr:
                raise
            _p(f"OCR skipped: {exc}")
            logger.warning("OCR skipped: %s", exc)
        finally:
            if ocr_path is not None:
                ocr_path.unlink(missing_ok=True)

    n_before = len(blocks)
    blocks = filter_running_headers(blocks, keep_headers=keep_headers)
    if not keep_headers and len(blocks) < n_before:
        _p(f"Stripped {n_before - len(blocks)} header/footer block(s)")

    _p(
        f"PDF ready: {len(blocks)} blocks, {page_count} page(s)"
        + (" · OCR" if used_ocr else "")
    )
    return ExtractedDoc(
        source_path=str(path),
        blocks=blocks,
        used_ocr=used_ocr,
        page_count=page_count,
    )
