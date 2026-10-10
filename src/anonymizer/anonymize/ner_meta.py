"""Metadata on Presidio RecognizerResult / EntityHit for spaCy FP tooling."""

from __future__ import annotations

from typing import Any

from presidio_analyzer import RecognizerResult

# Soft types that spaCy may only *propose* unless corroborated
SPACY_SOFT_TYPES = frozenset({"PERSON", "ORG", "LOCATION", "CITY"})

META_SOURCE = "anonymizer_source"
META_POS = "anonymizer_pos"
META_SINGLE_TOKEN = "anonymizer_single_token"
META_SPACY_LABEL = "anonymizer_spacy_label"
META_PROPOSAL = "anonymizer_proposal"
META_LANG = "anonymizer_lang"


def _meta(r: RecognizerResult) -> dict[str, Any]:
    md = getattr(r, "recognition_metadata", None)
    if md is None:
        md = {}
        r.recognition_metadata = md
    return md


def set_meta(r: RecognizerResult, **kwargs: Any) -> None:
    md = _meta(r)
    for k, v in kwargs.items():
        if v is None:
            continue
        md[k] = v


def get_meta(r: RecognizerResult, key: str, default: Any = None) -> Any:
    md = getattr(r, "recognition_metadata", None) or {}
    return md.get(key, default)


def set_source(r: RecognizerResult, source: str) -> None:
    set_meta(r, **{META_SOURCE: source})


def get_source(r: RecognizerResult) -> str:
    return str(get_meta(r, META_SOURCE) or "")


def is_spacy_source(r: RecognizerResult) -> bool:
    return get_source(r).startswith("spacy:")


def is_proposal(r: RecognizerResult) -> bool:
    return bool(get_meta(r, META_PROPOSAL))


def set_proposal(r: RecognizerResult, value: bool = True) -> None:
    set_meta(r, **{META_PROPOSAL: bool(value)})


def copy_result(
    r: RecognizerResult,
    *,
    start: int | None = None,
    end: int | None = None,
    entity_type: str | None = None,
    score: float | None = None,
) -> RecognizerResult:
    """Clone a result including recognition_metadata."""
    out = RecognizerResult(
        entity_type=entity_type if entity_type is not None else r.entity_type,
        start=r.start if start is None else start,
        end=r.end if end is None else end,
        score=r.score if score is None else score,
        analysis_explanation=getattr(r, "analysis_explanation", None),
        recognition_metadata=dict(getattr(r, "recognition_metadata", None) or {}),
    )
    return out
