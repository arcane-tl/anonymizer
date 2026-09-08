"""Extraction tests for text and synthetic docs."""

from pathlib import Path

import pytest

from anonymizer.extract import extract_document
from anonymizer.extract.pdf import is_thin_text
from anonymizer.extract.text import extract_text_file
from anonymizer.models import BlockKind
from anonymizer.util.files import (
    SUPPORTED_TYPES_README_URL,
    collect_inputs,
    default_output_path,
    unsupported_type_message,
)


def test_extract_text_headings(tmp_path: Path):
    p = tmp_path / "sample.md"
    p.write_text("# Title\n\nHello world.\n\n## Section\n\n- item one\n", encoding="utf-8")
    doc = extract_text_file(p)
    kinds = [b.kind for b in doc.blocks]
    assert BlockKind.HEADING in kinds
    assert any(b.level == 1 for b in doc.blocks if b.kind == BlockKind.HEADING)


def test_thin_text_heuristic():
    assert is_thin_text(2, 10) is True
    assert is_thin_text(1, 500) is False


def test_collect_and_output_paths(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hi", encoding="utf-8")
    assert collect_inputs(f) == [f]
    assert default_output_path(f).name == "a.anonymized.md"
    assert default_output_path(f, mode="strict").name == "a.anonymized.md"
    assert default_output_path(f, mode="extract").name == "a.md"
    # Never overwrite a .md source in extract mode
    md = tmp_path / "note.md"
    md.write_text("x", encoding="utf-8")
    assert default_output_path(md, mode="extract").name == "note.extracted.md"
    out = default_output_path(f, tmp_path / "out")
    assert out == tmp_path / "out" / "a.anonymized.md"


def test_unsupported_type_message_pages_and_gdoc():
    pages = unsupported_type_message(".pages", path_hint="Brief.pages")
    assert pages.startswith("Unsupported file type")
    assert "Brief.pages" in pages
    assert ".pages" in pages
    assert "Pages" in pages
    assert "Export To" in pages
    assert "PDF" in pages and "docx" in pages.lower()
    # URL alone on final line so terminals can auto-link it
    assert pages.rstrip().endswith(SUPPORTED_TYPES_README_URL)
    assert "\n\n" in pages  # readable multi-line layout

    gdoc = unsupported_type_message(".gdoc", path_hint="Notes.gdoc")
    assert "Notes.gdoc" in gdoc
    assert "Google Docs" in gdoc
    assert "Download" in gdoc
    assert gdoc.rstrip().endswith(SUPPORTED_TYPES_README_URL)

    legacy = unsupported_type_message("doc")
    assert ".doc" in legacy
    assert "docx" in legacy.lower()


def test_collect_inputs_rejects_pages(tmp_path: Path):
    p = tmp_path / "Brief.pages"
    p.write_bytes(b"not a real pages file")
    with pytest.raises(ValueError, match="Pages|Export To|supported") as ei:
        collect_inputs(p)
    assert SUPPORTED_TYPES_README_URL in str(ei.value)


def test_collect_inputs_rejects_gdoc(tmp_path: Path):
    p = tmp_path / "Notes.gdoc"
    p.write_text('{"url": "https://docs.google.com/document/d/x"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Google Docs|Download|supported") as ei:
        collect_inputs(p)
    assert ".gdoc" in str(ei.value)
    assert SUPPORTED_TYPES_README_URL in str(ei.value)


def test_extract_document_rejects_unsupported(tmp_path: Path):
    p = tmp_path / "slide.pptx"
    p.write_bytes(b"PK")
    with pytest.raises(ValueError, match="supported") as ei:
        extract_document(p)
    assert ".pptx" in str(ei.value)
    assert SUPPORTED_TYPES_README_URL in str(ei.value)


def test_collect_inputs_expands_tilde(tmp_path: Path, monkeypatch):
    """Shell-style ~/paths must resolve (Typer does not expand ~)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "doc.txt"
    f.write_text("hello", encoding="utf-8")
    found = collect_inputs(Path("~/doc.txt"))
    assert found == [f.expanduser()]
    assert found[0].is_file()


def test_collect_inputs_expands_tilde_directory(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    docs = tmp_path / "docs"
    docs.mkdir()
    a = docs / "a.txt"
    b = docs / "b.md"
    a.write_text("a", encoding="utf-8")
    b.write_text("b", encoding="utf-8")
    (docs / "skip.bin").write_bytes(b"\x00")
    found = collect_inputs(Path("~/docs"))
    assert found == [a.expanduser(), b.expanduser()]


def test_default_output_path_expands_tilde_out_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    src = tmp_path / "src.txt"
    src.write_text("x", encoding="utf-8")
    out = default_output_path(src, Path("~/exports"))
    assert out == (tmp_path / "exports" / "src.anonymized.md").expanduser()
    assert out.parent.is_dir()
    # Must not create a literal "~" directory under cwd
    assert out.parts[0] != "~"
    assert "~" not in out.parts


def test_extract_docx_fixture():
    path = Path(__file__).parent / "fixtures" / "sample_en.docx"
    if not path.exists():
        return
    from anonymizer.extract.docx_extract import extract_docx

    doc = extract_docx(path)
    assert doc.blocks
    assert any("Alice" in b.text or "Acme" in b.text for b in doc.blocks)


def test_extract_pdf_fixture():
    path = Path(__file__).parent / "fixtures" / "sample_en.pdf"
    if not path.exists():
        return
    from anonymizer.extract.pdf import extract_pdf

    doc = extract_pdf(path, no_ocr=True)
    assert doc.blocks
    assert any("Bob" in b.text for b in doc.blocks)
