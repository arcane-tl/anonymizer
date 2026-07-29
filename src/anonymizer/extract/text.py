"""Plain text and Markdown extraction."""

from __future__ import annotations

from pathlib import Path

from anonymizer.models import BlockKind, ExtractedDoc, TextBlock


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_text_file(path: Path) -> ExtractedDoc:
    content = _read_text(path)
    # Split on blank lines into paragraphs; keep single newlines inside as space-join optional
    # For MD/TXT preserve line structure as paragraphs of non-empty lines grouped by blank lines
    blocks: list[TextBlock] = []
    paragraphs = content.split("\n\n")
    for para in paragraphs:
        text = para.strip("\n")
        if not text.strip():
            continue
        # Detect markdown AT
        stripped = text.lstrip()
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            level = min(max(hashes, 1), 6)
            heading_text = stripped[hashes:].strip()
            blocks.append(
                TextBlock(text=heading_text, kind=BlockKind.HEADING, level=level)
            )
        elif stripped.startswith(("- ", "* ", "+ ")) or (
            len(stripped) > 2 and stripped[0].isdigit() and stripped[1:3] in (". ", ") ")
        ):
            blocks.append(TextBlock(text=text, kind=BlockKind.LIST_ITEM))
        else:
            blocks.append(TextBlock(text=text, kind=BlockKind.PARAGRAPH))
    if not blocks and content.strip():
        blocks.append(TextBlock(text=content.strip(), kind=BlockKind.PARAGRAPH))
    return ExtractedDoc(source_path=str(path), blocks=blocks)
