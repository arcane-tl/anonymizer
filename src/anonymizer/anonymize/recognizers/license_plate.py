"""Broader vehicle registration plate recognizer (EU / US / generic).

Used on English NLP passes. Finnish ``ABC-123`` shapes are handled by
:mod:`fi_plate` when the FI pass runs; on EN-only docs this recognizer also
covers FI-like dashed forms as ``LICENSE_PLATE``.

Loose generic patterns require nearby plate/registration context.
"""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

_CONTEXT_RE = re.compile(
    r"(?i)\b("
    r"licence\s*plate|license\s*plate|number\s*plate|reg(?:istration)?(?:\s+n(?:umbe)?r|\.?|no\.?)?|"
    r"vehicle\s+(?:reg|plate)|plate\s*no\.?|tag\s*number|"
    r"rekisterinumero|rekisteri|kilpi"
    r")\b"
)
_CONTEXT_WINDOW = 40

# Label / boilerplate letter groups
_FORBIDDEN = frozenset(
    {
        "ID",
        "OK",
        "NO",
        "YES",
        "PDF",
        "URL",
        "HTTP",
        "WWW",
        "API",
        "VAT",
        "IBAN",
        "VIN",
        "THE",
        "AND",
        "FOR",
        "OR",
    }
)

# US: ABC-1234, ABC1234, 123-ABC, 7ABC123 (state-style alphanumerics)
_US_DASHED = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([A-Z]{2,3})"
    r"-"
    r"(\d{3,4})"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_US_DIGITS_LETTERS = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(\d{1,4})"
    r"-"
    r"([A-Z]{2,3})"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_US_COMPACT = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([A-Z]{3}\d{3,4}|\d[A-Z]{3}\d{3}|[A-Z]{2}\d{4}|\d{3}[A-Z]{3})"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# EU-ish: longer digit runs, space-separated, regional prefixes
_EU_DASHED_LONG = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([A-Z]{1,3})"
    r"-"
    r"(\d{4,5})"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_EU_SPACED = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([A-Z]{1,3})"
    r"[ \u00a0]"
    r"(\d{2,5})"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
# e.g. M-AB 1234, B-MW 1234 (DE-style regional)
_EU_REGIONAL = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([A-Z]{1,3})"
    r"-"
    r"([A-Z]{1,2})"
    r"[ \u00a0]"
    r"(\d{2,4})"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# FI-like on EN-only docs: ABC-123 / AB-12 (also covered by FiPlate when FI runs)
_FI_LIKE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([A-Z]{2,3})"
    r"-"
    r"(\d{1,3})"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Generic LLDDLL / LL-DDD needing context
_GENERIC_COMPACT = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([A-Z]{2}\d{2}[A-Z]{2}|\d{2}[A-Z]{2}\d{2})"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def _has_context(text: str, start: int, end: int) -> bool:
    lo = max(0, start - _CONTEXT_WINDOW)
    hi = min(len(text), end + _CONTEXT_WINDOW)
    return bool(_CONTEXT_RE.search(text[lo:hi]))


def _letters_ok(letters: str) -> bool:
    u = letters.upper()
    return u not in _FORBIDDEN and len(u) >= 1


def find_license_plates(text: str) -> list[tuple[int, int, str, float, str]]:
    """Return (start, end, surface, score, pattern_name)."""
    hits: list[tuple[int, int, str, float, str]] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(start < e and end > s for s, e, *_ in hits)

    def _add(start: int, end: int, surface: str, score: float, name: str) -> None:
        if _overlaps(start, end):
            return
        hits.append((start, end, surface, score, name))

    for m in _EU_REGIONAL.finditer(text):
        if _letters_ok(m.group(1)) and _letters_ok(m.group(2)):
            _add(m.start(), m.end(), m.group(0), 0.9, "eu_regional")

    for m in _US_DASHED.finditer(text):
        if _letters_ok(m.group(1)):
            _add(m.start(), m.end(), m.group(0), 0.92, "us_dashed")

    for m in _US_DIGITS_LETTERS.finditer(text):
        if _letters_ok(m.group(2)):
            _add(m.start(), m.end(), m.group(0), 0.9, "us_digits_letters")

    for m in _EU_DASHED_LONG.finditer(text):
        if _letters_ok(m.group(1)):
            _add(m.start(), m.end(), m.group(0), 0.88, "eu_dashed_long")

    for m in _EU_SPACED.finditer(text):
        if _letters_ok(m.group(1)):
            _add(m.start(), m.end(), m.group(0), 0.85, "eu_spaced")

    for m in _US_COMPACT.finditer(text):
        _add(m.start(), m.end(), m.group(0), 0.86, "us_compact")

    for m in _FI_LIKE.finditer(text):
        if _letters_ok(m.group(1)):
            _add(m.start(), m.end(), m.group(0), 0.84, "fi_like")

    for m in _GENERIC_COMPACT.finditer(text):
        if not _has_context(text, m.start(), m.end()):
            continue
        _add(m.start(), m.end(), m.group(0), 0.75, "generic_context")

    hits.sort(key=lambda h: h[0])
    return hits


class LicensePlateRecognizer(EntityRecognizer):
    """Detect EU / US / generic registration plates (English docs)."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["LICENSE_PLATE"],
            supported_language="en",
            name="LicensePlateRecognizer",
        )

    def load(self) -> None:
        return

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: NlpArtifacts = None,  # noqa: ANN001
        regex_flags: Optional[int] = None,  # noqa: ARG002
    ) -> List[RecognizerResult]:
        if entities and "LICENSE_PLATE" not in entities:
            return []
        results: list[RecognizerResult] = []
        for start, end, _, score, pname in find_license_plates(text):
            results.append(
                RecognizerResult(
                    entity_type="LICENSE_PLATE",
                    start=start,
                    end=end,
                    score=score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=score,
                        pattern_name=pname,
                        pattern=pname,
                        validation_result=True,
                    ),
                )
            )
        return results
