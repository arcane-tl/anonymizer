"""Markdown → reflowed text PDF (distinct from native black-box redaction)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from anonymizer.output.md_pdf import strip_yaml_front_matter, write_pdf_from_markdown
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
