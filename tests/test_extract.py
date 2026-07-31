"""Extraction tests for text and synthetic docs."""

from pathlib import Path

from anonymizer.extract.pdf import is_thin_text
from anonymizer.extract.text import extract_text_file
from anonymizer.models import BlockKind
from anonymizer.util.files import collect_inputs, default_output_path


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
