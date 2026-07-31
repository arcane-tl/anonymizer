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
        # Ensure list marker
        stripped = text.lstrip()
        if stripped.startswith(("- ", "* ", "+ ")):
            return text
        if len(stripped) > 2 and stripped[0].isdigit() and stripped[1:3] in (". ", ") "):
            return text
        return f"- {text}"
    if block.kind == BlockKind.TABLE_CELL:
        return text
    return text


def render_markdown(
    source: Path | str,
    blocks: list[TextBlock],
    result: AnonymizeResult,
    *,
    used_ocr: bool = False,
) -> str:
    fm = {
        "source": str(source),
        "anonymized_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": "anonymizer",
        "tool_version": __version__,
        "mode": result.mode,
        "lang_mode": result.language.mode,
        "detected_languages": result.language.detected,
        "nlp_passes": result.language.nlp_passes,
        "entity_counts": result.entity_counts,
        "used_ocr": used_ocr,
    }
    # sort_keys for stable output in tests
    yaml_body = yaml.safe_dump(fm, sort_keys=True, allow_unicode=True).strip()
    body_parts = [block_to_markdown(b) for b in blocks if b.text.strip()]
    body = "\n\n".join(body_parts)
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
    return render_markdown(
        doc.source_path,
        new_blocks,
        result,
        used_ocr=doc.used_ocr,
    )
