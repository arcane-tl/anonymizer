"""Finnish vehicle registration plate recognizer."""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# Modern passenger plates: ABC-123 (3 letters + 1–3 digits). Also AB-123, ABC-12.
# Letters A–Z (Finnish plates do not use Å/Ä/Ö). Case-insensitive.
_PLATE_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([A-Z]{2,3})"
    r"-"
    r"(\d{1,3})"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Without hyphen (less common in prose, still seen): ABC123
_PLATE_NO_HYPHEN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([A-Z]{3})"
    r"(\d{1,3})"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Letters not used on Finnish plates (approximate filter for no-hyphen false positives)
_FORBIDDEN = set("ÅÄÖåäö")


def is_plausible_plate(letters: str, digits: str) -> bool:
    if any(c in _FORBIDDEN for c in letters):
        return False
    if not letters.isalpha() or not digits.isdigit():
        return False
    if len(letters) not in (2, 3):
        return False
    if not (1 <= len(digits) <= 3):
        return False
    # Avoid matching things like "ID-1" or "OK-1" used as labels — weak filter
    if letters.upper() in {"ID", "OK", "NO", "YES", "PDF", "URL", "HTTP", "WWW"}:
        return False
    return True


def find_fi_plates(text: str) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []
    for m in _PLATE_RE.finditer(text):
        letters, digits = m.group(1), m.group(2)
        if is_plausible_plate(letters, digits):
            hits.append((m.start(), m.end(), m.group(0)))
    for m in _PLATE_NO_HYPHEN.finditer(text):
        letters, digits = m.group(1), m.group(2)
        if not is_plausible_plate(letters, digits):
            continue
        # Prefer hyphenated form if already captured
        span = (m.start(), m.end())
        if any(s <= span[0] and span[1] <= e for s, e, _ in hits):
            continue
        hits.append((m.start(), m.end(), m.group(0)))
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
