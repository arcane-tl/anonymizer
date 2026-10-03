"""GFM table emission from consecutive TABLE_CELL blocks."""

from __future__ import annotations

from anonymizer.models import AnonymizeResult, BlockKind, LanguageDecision, TextBlock
from anonymizer.output.markdown import (
    block_to_markdown,
    blocks_to_markdown_body,
    render_markdown,
)


def test_list_item_normalizes_unicode_bullet():
    assert block_to_markdown(
        TextBlock(text="• Delivery soon", kind=BlockKind.LIST_ITEM)
    ) == "- Delivery soon"
    assert block_to_markdown(
        TextBlock(text="- Already md", kind=BlockKind.LIST_ITEM)
    ) == "- Already md"


def test_blocks_to_markdown_body_groups_gfm_table():
    blocks = [
        TextBlock(text="Report", kind=BlockKind.HEADING, level=1),
        TextBlock(text="Name | Role", kind=BlockKind.TABLE_CELL),
        TextBlock(text="Alice | Lead", kind=BlockKind.TABLE_CELL),
        TextBlock(text="Bob | Dev", kind=BlockKind.TABLE_CELL),
        TextBlock(text="Footer note.", kind=BlockKind.PARAGRAPH),
    ]
    body = blocks_to_markdown_body(blocks)
    assert body.startswith("# Report")
    assert "| Name | Role |" in body
    assert "| --- | --- |" in body
    assert "| Alice | Lead |" in body
    assert "| Bob | Dev |" in body
    assert "Footer note." in body
    # Two separate tables if interrupted
    blocks2 = [
        TextBlock(text="A | B", kind=BlockKind.TABLE_CELL),
        TextBlock(text="Mid", kind=BlockKind.PARAGRAPH),
        TextBlock(text="C | D", kind=BlockKind.TABLE_CELL),
    ]
    body2 = blocks_to_markdown_body(blocks2)
    assert body2.count("| --- | --- |") == 2


def test_render_markdown_includes_gfm_table():
    blocks = [
        TextBlock(text="Col1 | Col2", kind=BlockKind.TABLE_CELL),
        TextBlock(text="x | y", kind=BlockKind.TABLE_CELL),
    ]
    result = AnonymizeResult(
        anonymized_text="",
        entity_counts={},
        mapping={},
        language=LanguageDecision(mode="auto", detected=["en"], nlp_passes=["en"]),
        mode="extract",
    )
    md = render_markdown("t.docx", blocks, result)
    assert "| Col1 | Col2 |" in md
    assert "| --- | --- |" in md
    assert "| x | y |" in md
