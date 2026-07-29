"""PDF extraction with optional OCR."""

from __future__ import annotations

import logging
from pathlib import Path

from anonymizer.anonymize.language import tesseract_lang_string
from anonymizer.extract.ocr import ocr_pdf_to_searchable
from anonymizer.models import BlockKind, ExtractedDoc, TextBlock

logger = logging.getLogger(__name__)

# Heuristic: average chars per page below this → try OCR
THIN_TEXT_CHARS_PER_PAGE = 40


def _extract_with_pymupdf(path: Path) -> tuple[list[TextBlock], int, int]:
    import fitz

    doc = fitz.open(path)
    blocks: list[TextBlock] = []
    total_chars = 0
    try:
        for page in doc:
            # "blocks" mode: list of (x0,y0,x1,y1, text, block_no, block_type)
            page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:  # text
                    continue
                lines: list[str] = []
                for line in block.get("lines", []):
                    spans = [s.get("text", "") for s in line.get("spans", [])]
                    line_text = "".join(spans).strip()
                    if line_text:
                        lines.append(line_text)
                para = "\n".join(lines).strip()
                if para:
                    total_chars += len(para)
                    blocks.append(TextBlock(text=para, kind=BlockKind.PARAGRAPH))
            # Fallback if dict empty
            if not page_dict.get("blocks"):
                plain = page.get_text("text").strip()
                if plain:
                    total_chars += len(plain)
                    for para in plain.split("\n\n"):
                        p = para.strip()
                        if p:
                            blocks.append(TextBlock(text=p, kind=BlockKind.PARAGRAPH))
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
) -> ExtractedDoc:
    blocks, page_count, total_chars = _extract_with_pymupdf(path)
    used_ocr = False

    need_ocr = force_ocr or (not no_ocr and is_thin_text(page_count, total_chars))
    if need_ocr and not no_ocr:
        tess_lang = tesseract_lang_string(lang_flag)
        logger.info("Running OCR on %s (langs=%s)", path, tess_lang)
        ocr_path = None
        try:
            ocr_path = ocr_pdf_to_searchable(path, tesseract_langs=tess_lang)
            blocks, page_count, total_chars = _extract_with_pymupdf(ocr_path)
            used_ocr = True
        except RuntimeError as exc:
            if force_ocr:
                raise
            logger.warning("OCR skipped: %s", exc)
        finally:
            if ocr_path is not None:
                ocr_path.unlink(missing_ok=True)

    return ExtractedDoc(
        source_path=str(path),
        blocks=blocks,
        used_ocr=used_ocr,
        page_count=page_count,
    )
