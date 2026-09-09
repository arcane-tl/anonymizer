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

# Applied via Document.apply_css(append=True) on pymupdf Markdown docs.
# Keep built-in fonts; avoid embedding large system font files.
DEFAULT_MD_PDF_CSS = """
@page {
  margin: 54pt 54pt 54pt 54pt;
}
body {
  font-size: 11pt;
  line-height: 1.45;
}
h1 {
  font-size: 20pt;
  margin: 0 0 14pt 0;
}
h2 {
  font-size: 15pt;
  margin: 16pt 0 8pt 0;
}
h3 {
  font-size: 13pt;
  margin: 14pt 0 6pt 0;
}
h4, h5, h6 {
  font-size: 12pt;
  margin: 12pt 0 6pt 0;
}
p {
  margin: 0 0 8pt 0;
}
ul, ol {
  margin: 4pt 0 10pt 0;
  padding-left: 22pt;
}
li {
  margin: 2pt 0;
}
blockquote {
  margin: 8pt 0 8pt 14pt;
  color: #333333;
}
code, pre {
  font-size: 9.5pt;
}
pre {
  margin: 8pt 0;
  padding: 6pt 8pt;
}
table {
  border-collapse: collapse;
  margin: 10pt 0;
  width: 100%;
}
th, td {
  border: 1px solid #666666;
  padding: 4pt 8pt;
  vertical-align: top;
}
th {
  font-weight: bold;
  background-color: #eeeeee;
}
hr {
  margin: 14pt 0;
  border: none;
  border-top: 1px solid #999999;
}
"""


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
    css: str | None = DEFAULT_MD_PDF_CSS,
) -> Path:
    """Write a PDF from Markdown body text using pymupdf's Markdown → PDF path.

    Requires pymupdf ≥ 1.28. Front matter is stripped. Returns *dest*.
    Pass ``css=None`` to skip stylesheet (engine defaults only).
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
        if css:
            try:
                doc.apply_css(css, append=True)
            except Exception:  # noqa: BLE001
                # Older or non-reflowable builds — still save unstyled MD PDF
                pass
        # open(..., filetype="md") yields a non-PDF document; save converts to PDF
        doc.save(dest)
    finally:
        doc.close()
    return dest
