"""Render anonymized Markdown to a reflowed text PDF (pymupdf Markdown engine).

This is distinct from native PDF black-box redaction (``pdf_redact.py``):
layout is rebuilt from Markdown, not preserved from the source PDF.
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONT_MATTER_RE = re.compile(
    r"\A---\s*\n.*?\n---\s*\n?",
    re.DOTALL,
)


def strip_yaml_front_matter(markdown: str) -> str:
    """Remove leading ``---`` YAML front matter so it is not printed in the PDF."""
    text = markdown.lstrip("\ufeff")
    if not text.startswith("---"):
        return text
    # Require a closing --- on its own line (same convention as render_markdown)
    m = _FRONT_MATTER_RE.match(text)
    if m:
        return text[m.end() :].lstrip("\n")
    return text


def write_pdf_from_markdown(
    markdown: str,
    dest: Path,
    *,
    page: str = "A4",
) -> Path:
    """Write a PDF from Markdown body text using pymupdf's Markdown → PDF path.

    Requires pymupdf ≥ 1.28. Front matter is stripped. Returns *dest*.
    """
    import pymupdf

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = strip_yaml_front_matter(markdown)
    if not body.strip():
        body = "_(empty document)_\n"

    # filetype="md" uses the built-in Markdown engine (pymupdf 1.28+)
    kwargs: dict = {"filetype": "md"}
    try:
        rect = pymupdf.paper_rect(page)
        kwargs["rect"] = rect
    except Exception:  # noqa: BLE001
        pass

    doc = pymupdf.open(stream=body.encode("utf-8"), **kwargs)
    try:
        # open(..., filetype="md") yields a non-PDF document; save converts to PDF
        doc.save(dest)
    finally:
        doc.close()
    return dest
