"""Shared data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BlockKind(str, Enum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST_ITEM = "list_item"
    TABLE_CELL = "table_cell"


@dataclass
class TextBlock:
    text: str
    kind: BlockKind = BlockKind.PARAGRAPH
    level: int | None = None  # heading level 1–6
    page: int | None = None  # 1-based page index when known (PDF)


@dataclass
class ExtractedDoc:
    source_path: str
    blocks: list[TextBlock] = field(default_factory=list)
    used_ocr: bool = False
    page_count: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def full_text(self) -> str:
        """Join blocks with blank lines for language detection / flat analysis."""
        parts: list[str] = []
        for b in self.blocks:
            t = b.text.strip()
            if t:
                parts.append(t)
        return "\n\n".join(parts)


@dataclass
class EntityHit:
    entity_type: str
    text: str
    start: int
    end: int
    score: float
    source: str = ""  # e.g. en_spacy, fi_spacy, pattern, denylist


@dataclass
class LanguageDecision:
    mode: str  # auto | forced
    detected: list[str]  # en, fi (what detector saw)
    nlp_passes: list[str]  # en and/or fi to run
    reason: str = ""


@dataclass
class AnonymizeResult:
    anonymized_text: str
    entity_counts: dict[str, int]
    mapping: dict[str, str]  # placeholder -> original
    language: LanguageDecision
    hits: list[EntityHit] = field(default_factory=list)
    # Operating mode: extract | standard | strict
    mode: str = "strict"
    # placeholder | remove — how spans were replaced in the body
    redact_style: str = "placeholder"
