"""Tests for native PDF/DOCX redaction and surface helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from anonymizer.anonymize.surfaces import (
    RedactSurface,
    surface_appears_in_text,
    surface_search_variants,
    surfaces_from_mapping,
)
from anonymizer.output.docx_redact import redact_docx
from anonymizer.output.native import (
    normalize_output_format,
    wants_markdown,
    wants_native,
    write_native_redacted,
)
from anonymizer.output.native_stats import NativeRedactStats
from anonymizer.output.pdf_redact import redact_pdf


def test_surfaces_longest_first() -> None:
    m = {
        "[ORG_1]": "ACME",
        "[ORG_2]": "ACME Corp",
        "[PERSON_1]": "Alice",
    }
    surfs = surfaces_from_mapping(m)
    clears = [s.clear for s in surfs]
    assert clears[0] == "ACME Corp"  # longest first
    assert set(clears) == {"ACME Corp", "ACME", "Alice"}


def test_surface_variants_nbsp() -> None:
    v = surface_search_variants("Foo\u00a0Bar")
    assert "Foo\u00a0Bar" in v
    assert "Foo Bar" in v


def test_surface_variants_soft_hyphen() -> None:
    v = surface_search_variants("Foo\u00adBar")
    assert "FooBar" in v
    assert "Foo-Bar" in v
    assert "Foo-\nBar" in v


def test_surface_variants_hyphen_linebreak() -> None:
    v = surface_search_variants("ETA-maat")
    assert "ETA-\nmaat" in v
    assert "ETAmaat" in v


def test_surface_variants_soft_wrap_newline() -> None:
    v = surface_search_variants("Alice Wonderland")
    assert "Alice\nWonderland" in v


def test_surface_appears_in_text_normalized() -> None:
    assert surface_appears_in_text("Hello Alice\nWonderland here", "Alice Wonderland")
    assert surface_appears_in_text("ETA-\nmaat Oyj", "ETA-maat")
    assert not surface_appears_in_text("nothing here", "Alice Wonderland")


def test_native_stats_is_clean_and_summary() -> None:
    clean = NativeRedactStats(
        format="pdf",
        surfaces_total=2,
        surfaces_found=2,
        hit_count=3,
        verified=True,
        residuals_found=0,
    )
    assert clean.is_clean
    assert "verified clean" in clean.summary()

    dirty = NativeRedactStats(
        format="pdf",
        surfaces_total=2,
        surfaces_found=2,
        hit_count=2,
        verified=True,
        residuals_found=1,
        residuals=["Secret"],
    )
    assert not dirty.is_clean
    assert "1 residual" in dirty.summary()


def test_normalize_output_format() -> None:
    assert normalize_output_format(None) == "md"
    assert normalize_output_format("native") == "source"
    assert normalize_output_format("BOTH") == "both"
    with pytest.raises(ValueError):
        normalize_output_format("excel")


def test_wants_flags() -> None:
    assert wants_markdown("md") and not wants_native("md")
    assert wants_native("source") and not wants_markdown("source")
    assert wants_markdown("both") and wants_native("both")


def test_pdf_redact_removes_cleartext(tmp_path: Path) -> None:
    import pymupdf as fitz

    src = tmp_path / "in.pdf"
    dest = tmp_path / "out.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Contact Alice Wonderland at HQ.")
    doc.save(src)
    doc.close()

    surfaces = [
        RedactSurface(clear="Alice Wonderland", placeholder="[PERSON_1]"),
    ]
    stats = redact_pdf(src, surfaces, dest)
    assert stats.surfaces_found == 1
    assert stats.hit_count >= 1
    assert stats.verified
    assert stats.residuals_found == 0
    assert stats.is_clean
    assert dest.is_file()

    after = fitz.open(dest)
    text = after[0].get_text()
    after.close()
    assert "Alice Wonderland" not in text


def test_pdf_redact_hyphenated_linebreak(tmp_path: Path) -> None:
    """Hyphenated wrap ``ETA-\\nmaat`` should match cleartext ``ETA-maat``."""
    import pymupdf as fitz

    src = tmp_path / "hyph.pdf"
    dest = tmp_path / "hyph.out.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "ETA-")
    page.insert_text((72, 86), "maat Oyj signed.")
    doc.save(src)
    doc.close()

    surfaces = [RedactSurface(clear="ETA-maat", placeholder="[ORG_1]")]
    stats = redact_pdf(src, surfaces, dest)
    assert stats.surfaces_found == 1
    assert stats.hit_count >= 1
    assert stats.verified
    assert stats.residuals_found == 0

    after = fitz.open(dest)
    text = after[0].get_text()
    after.close()
    assert "ETA-" not in text
    assert "maat" not in text


def test_pdf_scrub_forms_and_annots(tmp_path: Path) -> None:
    import pymupdf as fitz

    src = tmp_path / "form.pdf"
    dest = tmp_path / "form.out.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Body Alice Wonderland ok.")
    widget = fitz.Widget()
    widget.field_name = "full_name"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.field_value = "Alice Wonderland"
    widget.rect = fitz.Rect(72, 100, 300, 120)
    page.add_widget(widget)
    # Sticky note / FreeText whose content is NOT a searched surface — still
    # must be wiped by the aggressive annotation scrub pass.
    page.add_freetext_annot(
        fitz.Rect(72, 140, 300, 160), "Internal review: escalate to legal"
    )
    page.add_text_annot(fitz.Point(72, 200), "Hidden reviewer Carol")
    doc.set_metadata({"author": "Alice Wonderland", "title": "Secret"})
    doc.save(src)
    doc.close()

    surfaces = [
        RedactSurface(clear="Alice Wonderland", placeholder="[PERSON_1]"),
    ]
    stats = redact_pdf(src, surfaces, dest)
    assert stats.widgets_scrubbed >= 1
    assert stats.annotations_scrubbed >= 1
    assert stats.verified

    after = fitz.open(dest)
    text = after[0].get_text()
    meta = after.metadata or {}
    widgets = list(after[0].widgets() or [])
    annots = list(after[0].annots() or [])
    after.close()

    assert "Alice Wonderland" not in text
    assert "escalate to legal" not in text
    assert "Carol" not in text
    assert not widgets
    assert not annots
    assert not (meta.get("author") or "").strip()
    assert not (meta.get("title") or "").strip()
    assert stats.residuals_found == 0


def test_docx_redact_placeholder(tmp_path: Path) -> None:
    from docx import Document

    src = tmp_path / "in.docx"
    dest = tmp_path / "out.docx"
    d = Document()
    d.add_paragraph("Signed by Alice Wonderland on behalf of ACME Corp.")
    d.save(src)

    surfaces = [
        RedactSurface(clear="Alice Wonderland", placeholder="[PERSON_1]"),
        RedactSurface(clear="ACME Corp", placeholder="[ORG_1]"),
    ]
    stats = redact_docx(src, surfaces, dest, style="placeholder")
    assert stats.surfaces_found == 2
    assert stats.verified
    assert stats.residuals_found == 0
    assert dest.is_file()

    out = Document(str(dest))
    body = "\n".join(p.text for p in out.paragraphs)
    assert "Alice Wonderland" not in body
    assert "[PERSON_1]" in body
    assert "[ORG_1]" in body


def test_docx_redact_remove(tmp_path: Path) -> None:
    from docx import Document

    src = tmp_path / "in.docx"
    dest = tmp_path / "out.docx"
    d = Document()
    d.add_paragraph("Name: Alice Wonderland.")
    d.save(src)

    surfaces = [RedactSurface(clear="Alice Wonderland", placeholder="[PERSON_1]")]
    redact_docx(src, surfaces, dest, style="remove")
    body = "\n".join(p.text for p in Document(str(dest)).paragraphs)
    assert "Alice Wonderland" not in body
    assert "[PERSON_1]" not in body


def test_docx_preserves_unaffected_run_styles(tmp_path: Path) -> None:
    from docx import Document

    src = tmp_path / "styled.docx"
    dest = tmp_path / "styled.out.docx"
    d = Document()
    p = d.add_paragraph()
    r0 = p.add_run("Hello ")
    r0.bold = True
    r1 = p.add_run("Alice")
    r1.italic = True
    r2 = p.add_run(" Wonderland")
    r2.italic = True
    r3 = p.add_run(" signed.")
    r3.bold = False
    d.save(src)

    surfaces = [RedactSurface(clear="Alice Wonderland", placeholder="[PERSON_1]")]
    stats = redact_docx(src, surfaces, dest, style="placeholder")
    assert stats.surfaces_found == 1
    assert stats.residuals_found == 0

    out = Document(str(dest))
    para = out.paragraphs[0]
    assert "Alice Wonderland" not in para.text
    assert "[PERSON_1]" in para.text
    assert para.runs[0].text == "Hello "
    assert para.runs[0].bold is True
    # Replacement lands in first affected run; later match runs cleared
    assert para.runs[1].text == "[PERSON_1]"
    assert para.runs[1].italic is True
    assert para.runs[-1].text == " signed."


def test_docx_redacts_header_and_table(tmp_path: Path) -> None:
    from docx import Document

    src = tmp_path / "hdr.docx"
    dest = tmp_path / "hdr.out.docx"
    d = Document()
    d.add_paragraph("Body without names.")
    header = d.sections[0].header
    # Force a real header part (unlink from previous) then set text via run.
    header.is_linked_to_previous = False
    hp = header.paragraphs[0]
    hp.text = ""
    hp.add_run("Confidential - Alice Wonderland")
    table = d.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Signed by Bob Builder"
    d.save(src)

    surfaces = [
        RedactSurface(clear="Alice Wonderland", placeholder="[PERSON_1]"),
        RedactSurface(clear="Bob Builder", placeholder="[PERSON_2]"),
    ]
    stats = redact_docx(src, surfaces, dest, style="placeholder")
    assert stats.surfaces_found == 2
    assert stats.residuals_found == 0

    out = Document(str(dest))
    hdr = out.sections[0].header.paragraphs[0].text
    assert "Alice Wonderland" not in hdr
    assert "[PERSON_1]" in hdr
    cell = out.tables[0].cell(0, 0).text
    assert "Bob Builder" not in cell
    assert "[PERSON_2]" in cell


def test_docx_redacts_comment_text(tmp_path: Path) -> None:
    from docx import Document

    src = tmp_path / "cmt.docx"
    dest = tmp_path / "cmt.out.docx"
    d = Document()
    d.add_paragraph("Visible body.")
    d.part.comments.add_comment(text="Call Bob Builder tomorrow", author="rev")
    d.save(src)

    surfaces = [RedactSurface(clear="Bob Builder", placeholder="[PERSON_1]")]
    stats = redact_docx(src, surfaces, dest, style="placeholder")
    # Comment parts can be quirky across python-docx versions; require either
    # a successful hit or a residual report (never silent).
    assert stats.verified
    out = Document(str(dest))
    comment_text = "\n".join(
        p.text for c in out.part.comments for p in c.paragraphs
    )
    if stats.surfaces_found:
        assert "Bob Builder" not in comment_text
        assert "[PERSON_1]" in comment_text
        assert stats.residuals_found == 0
    else:
        assert "Bob Builder" in comment_text
        assert stats.residuals_found >= 1


def test_fail_on_native_miss_gate_logic() -> None:
    """is_clean drives --fail-on-native-miss; match_rate drives min threshold."""
    clean = NativeRedactStats(
        format="pdf",
        surfaces_total=2,
        surfaces_found=2,
        verified=True,
        residuals_found=0,
    )
    assert clean.is_clean and clean.match_rate == 1.0

    missed = NativeRedactStats(
        format="pdf",
        surfaces_total=2,
        surfaces_found=1,
        surfaces_missed=1,
        missed=["Secret"],
        verified=True,
        residuals_found=0,
    )
    assert not missed.is_clean
    assert missed.match_rate == 0.5
    assert missed.match_rate < 1.0


def test_write_native_dispatch(tmp_path: Path) -> None:
    import pymupdf as fitz

    src = tmp_path / "x.pdf"
    dest = tmp_path / "x.anonymized.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Secret Bob Builder")
    doc.save(src)
    doc.close()

    stats = write_native_redacted(
        src, dest, {"[PERSON_1]": "Bob Builder"}, redact_style="placeholder"
    )
    assert stats is not None
    assert stats.format == "pdf"
    assert stats.verified
    assert dest.is_file()
