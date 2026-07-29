"""Document extractors."""

from __future__ import annotations

from pathlib import Path

from anonymizer.extract.docx_extract import extract_docx
from anonymizer.extract.pdf import extract_pdf
from anonymizer.extract.text import extract_text_file
from anonymizer.models import ExtractedDoc

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".text"}


def extract_document(
    path: Path,
    *,
    force_ocr: bool = False,
    no_ocr: bool = False,
    lang_flag: str = "auto",
) -> ExtractedDoc:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(
            path, force_ocr=force_ocr, no_ocr=no_ocr, lang_flag=lang_flag
        )
    if suffix == ".docx":
        return extract_docx(path)
    if suffix in {".txt", ".md", ".markdown", ".text"}:
        return extract_text_file(path)
    raise ValueError(
        f"Unsupported file type {suffix!r}. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
    )
