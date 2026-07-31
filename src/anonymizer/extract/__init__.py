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
    keep_headers: bool = False,
    progress=None,  # Callable[[str], None] | None
) -> ExtractedDoc:
    def _p(msg: str) -> None:
        if progress:
            progress(msg)

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        _p("Extracting text (PDF)…")
        return extract_pdf(
            path,
            force_ocr=force_ocr,
            no_ocr=no_ocr,
            lang_flag=lang_flag,
            keep_headers=keep_headers,
            progress=progress,
        )
    if suffix == ".docx":
        _p("Extracting text (DOCX)…")
        doc = extract_docx(path)
        _p(f"DOCX ready: {len(doc.blocks)} blocks")
        return doc
    if suffix in {".txt", ".md", ".markdown", ".text"}:
        _p("Reading plain text…")
        doc = extract_text_file(path)
        _p(f"Text ready: {len(doc.blocks)} blocks")
        return doc
    raise ValueError(
        f"Unsupported file type {suffix!r}. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
    )
