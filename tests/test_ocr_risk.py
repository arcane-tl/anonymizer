"""OCR coverage / residual image-risk reporting."""

from __future__ import annotations

from anonymizer.extract.pdf import THIN_TEXT_CHARS_PER_PAGE, _ocr_coverage_report
from anonymizer.models import BlockKind, TextBlock
from anonymizer.output.markdown import render_markdown
from anonymizer.models import AnonymizeResult, LanguageDecision


def test_ocr_coverage_flags_thin_pages() -> None:
    blocks = [
        TextBlock(text="x" * (THIN_TEXT_CHARS_PER_PAGE + 10), page=1),
        TextBlock(text="y" * 3, page=2),
        TextBlock(text="z" * 3, page=2),
    ]
    report = _ocr_coverage_report(
        blocks, 2, reason="thin text layer", langs="eng+fin"
    )
    assert report["used"] is True
    assert report["residual_image_risk"] is True
    assert report["reason"] == "thin text layer"
    assert report["low_coverage_pages"] == [2]
    assert report["page_chars"][1] >= THIN_TEXT_CHARS_PER_PAGE
    assert report["page_chars"][2] == 6


def test_markdown_front_matter_includes_ocr_risk() -> None:
    result = AnonymizeResult(
        anonymized_text="hi",
        entity_counts={},
        mapping={},
        language=LanguageDecision(mode="auto", detected=["en"], nlp_passes=["en"]),
    )
    md = render_markdown(
        "scan.pdf",
        [TextBlock(text="Hello", kind=BlockKind.PARAGRAPH)],
        result,
        used_ocr=True,
        ocr_meta={
            "residual_image_risk": True,
            "reason": "forced",
            "low_coverage_pages": [1, 3],
        },
    )
    assert "used_ocr: true" in md
    assert "ocr_residual_image_risk: true" in md
    assert "ocr_reason: forced" in md
    assert "ocr_low_coverage_pages:" in md
