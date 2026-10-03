"""Markdown → reflowed text PDF (distinct from native black-box redaction)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from anonymizer.output.md_pdf import (
    DEFAULT_MD_PDF_CSS,
    strip_yaml_front_matter,
    write_pdf_from_markdown,
)
from anonymizer.util.files import default_text_pdf_output_path


def test_strip_yaml_front_matter():
    md = "---\nsource: x.pdf\nmode: strict\n---\n\n# Title\n\nHello [PERSON_1].\n"
    body = strip_yaml_front_matter(md)
    assert body.startswith("# Title")
    assert "source:" not in body
    assert "[PERSON_1]" in body


def test_strip_yaml_front_matter_no_fm():
    assert strip_yaml_front_matter("# Hi\n") == "# Hi\n"


def test_default_text_pdf_output_path(tmp_path: Path):
    src = tmp_path / "note.txt"
    assert default_text_pdf_output_path(src).name == "note.anonymized.text.pdf"
    out = default_text_pdf_output_path(src, tmp_path / "exports")
    assert out == tmp_path / "exports" / "note.anonymized.text.pdf"
    assert out.parent.is_dir()


def test_write_pdf_from_markdown_contains_placeholders(tmp_path: Path):
    md = (
        "---\nsource: note.txt\ntool: anonymizer\n---\n\n"
        "# Memo\n\n"
        "Contact [PERSON_1] at [EMAIL_1].\n\n"
        "Company keeps ORG names in standard mode.\n"
    )
    dest = tmp_path / "note.anonymized.text.pdf"
    write_pdf_from_markdown(md, dest)
    assert dest.is_file()
    assert dest.stat().st_size > 500

    doc = pymupdf.open(dest)
    try:
        text = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()
    assert "[PERSON_1]" in text
    assert "[EMAIL_1]" in text
    assert "source: note.txt" not in text  # front matter stripped
    assert "Memo" in text


def test_write_pdf_from_markdown_empty_body(tmp_path: Path):
    dest = tmp_path / "empty.anonymized.text.pdf"
    write_pdf_from_markdown("---\nx: 1\n---\n\n", dest)
    assert dest.is_file()


def _span_sizes_by_text(pdf_path: Path) -> list[tuple[str, float]]:
    doc = pymupdf.open(pdf_path)
    out: list[tuple[str, float]] = []
    try:
        for page in doc:
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        t = (span.get("text") or "").strip()
                        if t:
                            out.append((t, float(span.get("size") or 0)))
    finally:
        doc.close()
    return out


def test_write_pdf_formats_headings_lists_tables(tmp_path: Path):
    md = """# Title Heading

## Section Two

Intro with **bold** and *italic*.

- Bullet one
- Bullet two

| Name | Role |
| --- | --- |
| Alice | Lead |
| Bob | Dev |
"""
    dest = tmp_path / "formatted.anonymized.text.pdf"
    write_pdf_from_markdown(md, dest, css=DEFAULT_MD_PDF_CSS)
    assert dest.is_file()

    spans = _span_sizes_by_text(dest)
    by_text = {t: sz for t, sz in spans}
    assert "Title Heading" in by_text
    assert "Section Two" in by_text
    # Heading hierarchy: H1 larger than H2 larger than body
    assert by_text["Title Heading"] > by_text["Section Two"]
    body_sizes = [sz for t, sz in spans if t.startswith("Intro")]
    assert body_sizes
    assert by_text["Section Two"] > body_sizes[0]

    text = "\n".join(t for t, _ in spans)
    assert "Bullet one" in text
    assert "Alice" in text and "Lead" in text
    # List markers rendered as bullet glyphs
    assert any(t.startswith("•") or "•" in t for t, _ in spans)


def test_default_css_constant_is_nonempty():
    assert "@page" in DEFAULT_MD_PDF_CSS
    assert "h1" in DEFAULT_MD_PDF_CSS
