"""Render anonymized content as Markdown with YAML front matter."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from anonymizer import __version__
from anonymizer.models import AnonymizeResult, BlockKind, ExtractedDoc, TextBlock


def block_to_markdown(block: TextBlock) -> str:
    text = block.text.rstrip()
    if block.kind == BlockKind.HEADING:
        level = block.level or 1
        return f"{'#' * level} {text}"
    if block.kind == BlockKind.LIST_ITEM:
        # Ensure a single Markdown list marker (avoid "- • item")
        stripped = text.lstrip()
        if stripped.startswith(("- ", "* ", "+ ")):
            return stripped
        if stripped[:2] in {"• ", "● ", "○ ", "▪ ", "▸ ", "► ", "· "}:
            return f"- {stripped[2:].lstrip()}"
        if len(stripped) > 2 and stripped[0].isdigit() and stripped[1:3] in (". ", ") "):
            return stripped
        return f"- {stripped}"
    if block.kind == BlockKind.TABLE_CELL:
        # Single row fallback (prefer blocks_to_markdown_body for GFM tables)
        cells = [c.strip() for c in text.split("|")]
        return "| " + " | ".join(cells) + " |"
    return text


def _table_row_cells(text: str) -> list[str]:
    """Split a pipe-joined table row into cells (DOCX extract format)."""
    raw = text.strip()
    if raw.startswith("|") and raw.endswith("|") and raw.count("|") >= 2:
        parts = [c.strip() for c in raw.strip("|").split("|")]
        return parts
    return [c.strip() for c in raw.split("|")]


def _gfm_table(rows: list[list[str]]) -> str:
    """Build a GitHub-flavoured Markdown table from cell rows."""
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]
    # Escape pipes inside cells lightly
    def cell(s: str) -> str:
        return s.replace("|", "\\|")

    header = norm[0]
    lines = [
        "| " + " | ".join(cell(c) for c in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in norm[1:]:
        lines.append("| " + " | ".join(cell(c) for c in row) + " |")
    return "\n".join(lines)


def blocks_to_markdown_body(blocks: list[TextBlock]) -> str:
    """Join blocks into a Markdown body, grouping consecutive TABLE_CELL rows."""
    parts: list[str] = []
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        nonlocal table_rows
        if table_rows:
            parts.append(_gfm_table(table_rows))
            table_rows = []

    for block in blocks:
        if not block.text.strip():
            continue
        if block.kind == BlockKind.TABLE_CELL:
            table_rows.append(_table_row_cells(block.text))
            continue
        flush_table()
        parts.append(block_to_markdown(block))
    flush_table()
    return "\n\n".join(parts)


def render_markdown(
    source: Path | str,
    blocks: list[TextBlock],
    result: AnonymizeResult,
    *,
    used_ocr: bool = False,
    ocr_meta: dict | None = None,
) -> str:
    fm: dict = {
        "source": str(source),
        "anonymized_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": "anonymizer",
        "tool_version": __version__,
        "mode": result.mode,
        "redact_style": result.redact_style,
        "lang_mode": result.language.mode,
        "detected_languages": result.language.detected,
        "nlp_passes": result.language.nlp_passes,
        "entity_counts": result.entity_counts,
        "used_ocr": used_ocr,
    }
    if used_ocr and ocr_meta:
        fm["ocr_residual_image_risk"] = bool(
            ocr_meta.get("residual_image_risk", True)
        )
        if ocr_meta.get("reason"):
            fm["ocr_reason"] = ocr_meta["reason"]
        low = ocr_meta.get("low_coverage_pages") or []
        if low:
            fm["ocr_low_coverage_pages"] = list(low)
    # sort_keys for stable output in tests
    yaml_body = yaml.safe_dump(fm, sort_keys=True, allow_unicode=True).strip()
    body = blocks_to_markdown_body(blocks)
    return f"---\n{yaml_body}\n---\n\n{body}\n"


def render_from_extracted(
    doc: ExtractedDoc,
    anon_block_texts: list[str],
    result: AnonymizeResult,
) -> str:
    new_blocks: list[TextBlock] = []
    for orig, text in zip(doc.blocks, anon_block_texts, strict=True):
        new_blocks.append(
            TextBlock(text=text, kind=orig.kind, level=orig.level)
        )
    ocr_meta = (doc.extra or {}).get("ocr") if doc.used_ocr else None
    return render_markdown(
        doc.source_path,
        new_blocks,
        result,
        used_ocr=doc.used_ocr,
        ocr_meta=ocr_meta if isinstance(ocr_meta, dict) else None,
    )
