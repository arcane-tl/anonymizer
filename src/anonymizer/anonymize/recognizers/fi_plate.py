"""Finnish vehicle registration plate recognizer.

Standard passenger / vanity form (Traficom): 2–3 letters + hyphen + 1–3 digits
(e.g. ``ABC-123``, ``AB-12``). Letters may include Å/Ä/Ö.

Motorcycle / special vanity may also use digit-leading ``123-ABC``.

No-hyphen ``ABC123`` is only accepted next to plate context cues (high FP risk).
"""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# Finnish plate letters (Latin + ÅÄÖ)
_LETTERS = r"A-Za-zÅÄÖåäö"
_LETTER_CLS = f"[{_LETTERS}]"

# Passenger / trailer / vanity: ABC-123, AB-12
_PLATE_RE = re.compile(
    rf"(?<![{_LETTERS}0-9])"
    rf"({_LETTER_CLS}{{2,3}})"
    r"-"
    r"(\d{1,3})"
    rf"(?![{_LETTERS}0-9])",
)

# Motorcycle / special: 123-ABC
_PLATE_MOTO_RE = re.compile(
    rf"(?<![{_LETTERS}0-9])"
    r"(\d{1,3})"
    r"-"
    rf"({_LETTER_CLS}{{2,3}})"
    rf"(?![{_LETTERS}0-9])",
)

# No hyphen — context-gated only
_PLATE_NO_HYPHEN = re.compile(
    rf"(?<![{_LETTERS}0-9])"
    rf"({_LETTER_CLS}{{3}})"
    r"(\d{1,3})"
    rf"(?![{_LETTERS}0-9])",
)

_CONTEXT_RE = re.compile(
    r"(?i)\b("
    r"rekisterinumero|rekisteri(?:nro|nro\.?)?|kilpi|ajoneuvo|"
    r"rek\.?\s*nro|reg(?:istration)?(?:\s+n(?:umbe)?r|\.?|no\.?)?|"
    r"licence\s*plate|license\s*plate|number\s*plate|plate\s*no\.?"
    r")\b"
)

_CONTEXT_WINDOW = 48

# Label-like letter groups — not plates
_FORBIDDEN_LETTERS = frozenset(
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
        "EU",
        "FI",
        "EN",
        "OR",
        "AND",
        "THE",
        "FOR",
        "TO",
        "OF",
    }
)


def _has_plate_context(text: str, start: int, end: int) -> bool:
    lo = max(0, start - _CONTEXT_WINDOW)
    hi = min(len(text), end + _CONTEXT_WINDOW)
    return bool(_CONTEXT_RE.search(text[lo:hi]))


def is_plausible_plate(letters: str, digits: str) -> bool:
    if not letters or not digits:
        return False
    if not digits.isdigit() or not (1 <= len(digits) <= 3):
        return False
    if len(letters) not in (2, 3):
        return False
    # Letters only from FI alphabet (already constrained by regex; double-check)
    if not re.fullmatch(rf"{_LETTER_CLS}+", letters):
        return False
    if letters.upper() in _FORBIDDEN_LETTERS:
        return False
    return True


def find_fi_plates(text: str) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []

    def _add(start: int, end: int, surface: str) -> None:
        span = (start, end)
        if any(s <= span[0] and span[1] <= e for s, e, _ in hits):
            return
        # Drop if overlapping an existing hit
        if any(start < e and end > s for s, e, _ in hits):
            return
        hits.append((start, end, surface))

    for m in _PLATE_RE.finditer(text):
        letters, digits = m.group(1), m.group(2)
        if is_plausible_plate(letters, digits):
            _add(m.start(), m.end(), m.group(0))

    for m in _PLATE_MOTO_RE.finditer(text):
        digits, letters = m.group(1), m.group(2)
        if is_plausible_plate(letters, digits):
            _add(m.start(), m.end(), m.group(0))

    for m in _PLATE_NO_HYPHEN.finditer(text):
        letters, digits = m.group(1), m.group(2)
        if not is_plausible_plate(letters, digits):
            continue
        if not _has_plate_context(text, m.start(), m.end()):
            continue
        _add(m.start(), m.end(), m.group(0))

    hits.sort(key=lambda h: h[0])
    return hits


class FiPlateRecognizer(EntityRecognizer):
    """Detect Finnish registration plates (e.g. ABC-123)."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["FI_LICENSE_PLATE"],
            supported_language="en",
            name="FiPlateRecognizer",
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
        if entities and "FI_LICENSE_PLATE" not in entities:
            return []
        results: list[RecognizerResult] = []
        for start, end, _ in find_fi_plates(text):
            results.append(
                RecognizerResult(
                    entity_type="FI_LICENSE_PLATE",
                    start=start,
                    end=end,
                    score=0.95,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=0.95,
                        pattern_name="fi_plate",
                        pattern="ABC-123",
                        validation_result=True,
                    ),
                )
            )
        return results
