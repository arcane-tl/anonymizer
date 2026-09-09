"""Unit tests for PDF → Markdown structure heuristics."""

from __future__ import annotations

from anonymizer.extract.pdf_structure import (
    block_font_stats,
    classify_pdf_block,
    heading_level_for_size,
    looks_like_list_item,
    page_median_font_size,
)
from anonymizer.models import BlockKind


def test_looks_like_list_item():
    assert looks_like_list_item("- Item")
    assert looks_like_list_item("* Item")
    assert looks_like_list_item("• Bullet")
    assert looks_like_list_item("1. First")
    assert looks_like_list_item("2) Second")
    assert not looks_like_list_item("Plain paragraph.")
    assert not looks_like_list_item("Version 1.2 release notes")


def test_heading_level_for_size():
    assert heading_level_for_size(18.0, 11.0) == 1
    assert heading_level_for_size(15.0, 11.0) == 2
    assert heading_level_for_size(13.0, 11.0) == 3
    assert heading_level_for_size(11.0, 11.0) is None


def test_classify_large_short_line_is_heading():
    kind, level = classify_pdf_block(
        "Supplier Agreement",
        max_size=18.0,
        page_median_size=11.0,
        bold=True,
    )
    assert kind == BlockKind.HEADING
    assert level == 1


def test_classify_list_marker():
    kind, level = classify_pdf_block(
        "• Delivery within 5 days",
        max_size=11.0,
        page_median_size=11.0,
    )
    assert kind == BlockKind.LIST_ITEM
    assert level is None


def test_classify_body_paragraph_not_heading():
    kind, level = classify_pdf_block(
        "This is a normal body paragraph that continues with enough words "
        "to look like running text rather than a title line in the document.",
        max_size=11.0,
        page_median_size=11.0,
        bold=False,
    )
    assert kind == BlockKind.PARAGRAPH
    assert level is None


def test_classify_shouty_section_header():
    kind, level = classify_pdf_block(
        "ASIAKAS",
        max_size=11.0,
        page_median_size=11.0,
        bold=False,
    )
    assert kind == BlockKind.HEADING
    assert level == 2


def test_classify_bold_short_near_body_size():
    kind, level = classify_pdf_block(
        "Payment terms",
        max_size=11.0,
        page_median_size=11.0,
        bold=True,
    )
    assert kind == BlockKind.HEADING
    assert level == 3


def test_page_median_font_size():
    assert page_median_font_size([10.0, 11.0, 18.0]) == 11.0
    assert page_median_font_size([]) == 11.0


def test_block_font_stats_bold_and_size():
    block = {
        "lines": [
            {
                "spans": [
                    {"text": "Title", "size": 18.0, "flags": 16, "font": "Helv-Bold"},
                ]
            }
        ]
    }
    size, bold = block_font_stats(block)
    assert size == 18.0
    assert bold is True


def test_extract_pdf_recovers_heading_and_list(tmp_path):
    """Round-trip: synthetic PDF with large title + bullet → structured blocks."""
    import pymupdf

    from anonymizer.extract.pdf import _extract_with_pymupdf
    from anonymizer.models import BlockKind

    pdf_path = tmp_path / "struct.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Service Agreement", fontsize=20, fontname="helv")
    page.insert_text((72, 120), "Body text at normal size for the page.", fontsize=11, fontname="helv")
    page.insert_text((72, 150), "• Deliver goods on time", fontsize=11, fontname="helv")
    doc.save(pdf_path)
    doc.close()

    blocks, pages, _ = _extract_with_pymupdf(pdf_path)
    assert pages == 1
    kinds = [b.kind for b in blocks]
    assert BlockKind.HEADING in kinds
    assert BlockKind.LIST_ITEM in kinds
    assert any(b.kind == BlockKind.PARAGRAPH for b in blocks)
