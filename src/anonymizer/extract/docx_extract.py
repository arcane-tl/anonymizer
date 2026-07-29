"""DOCX extraction via python-docx."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.table import Table
from docx.text.paragraph import Paragraph

from anonymizer.models import BlockKind, ExtractedDoc, TextBlock


def _heading_level(style_name: str | None) -> int | None:
    if not style_name:
        return None
    name = style_name.strip()
    lower = name.lower()
    if lower.startswith("heading"):
        parts = name.split()
        if len(parts) >= 2 and parts[-1].isdigit():
            return min(max(int(parts[-1]), 1), 6)
    # Finnish Word sometimes uses "Otsikko 1"
    if lower.startswith("otsikko"):
        parts = name.split()
        if len(parts) >= 2 and parts[-1].isdigit():
            return min(max(int(parts[-1]), 1), 6)
    return None


def _iter_block_items(parent):
    """Yield paragraphs and tables in document order."""
    from docx.oxml.ns import qn

    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def extract_docx(path: Path) -> ExtractedDoc:
    doc = Document(str(path))
    blocks: list[TextBlock] = []

    for item in _iter_block_items(doc):
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if not text:
                continue
            style_name = item.style.name if item.style else None
            level = _heading_level(style_name)
            if level is not None:
                blocks.append(
                    TextBlock(text=text, kind=BlockKind.HEADING, level=level)
                )
            elif style_name and "list" in style_name.lower():
                blocks.append(TextBlock(text=text, kind=BlockKind.LIST_ITEM))
            else:
                blocks.append(TextBlock(text=text, kind=BlockKind.PARAGRAPH))
        elif isinstance(item, Table):
            for row in item.rows:
                cells = [c.text.strip() for c in row.cells]
                # Deduplicate merged cell repeats
                seen: list[str] = []
                for c in cells:
                    if not seen or seen[-1] != c:
                        seen.append(c)
                line = " | ".join(c for c in seen if c)
                if line:
                    blocks.append(TextBlock(text=line, kind=BlockKind.TABLE_CELL))

    return ExtractedDoc(source_path=str(path), blocks=blocks)
