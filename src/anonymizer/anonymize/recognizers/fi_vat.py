"""Finnish VAT / ALV number recognizer (ALV-tunnus).

Format: ``FI`` + 8 digits (optional space or hyphen after FI), e.g. ``FI28567738``.
The 8 digits are the Y-tunnus without hyphen (7 digits + check digit).

Pattern-based only — no company-specific numbers.
"""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

from anonymizer.anonymize.recognizers.fi_business_id import is_valid_y_tunnus

# FI28567738 | FI 28567738 | FI-28567738
_VAT_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(FI)"
    r"[\s\-]?"
    r"(\d{8})"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def is_valid_fi_vat(digits8: str) -> bool:
    if len(digits8) != 8 or not digits8.isdigit():
        return False
    return is_valid_y_tunnus(digits8[:7], digits8[7])


def find_fi_vats(text: str) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []
    for m in _VAT_RE.finditer(text):
        digits = m.group(2)
        if not is_valid_fi_vat(digits):
            continue
        hits.append((m.start(), m.end(), m.group(0)))
    return hits


class FiVatRecognizer(EntityRecognizer):
    """Detect Finnish ALV / VAT numbers (FI + 8 digits with checksum)."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["FI_VAT"],
            supported_language="en",
            name="FiVatRecognizer",
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
        if entities and "FI_VAT" not in entities:
            return []
        results: list[RecognizerResult] = []
        for start, end, _ in find_fi_vats(text):
            results.append(
                RecognizerResult(
                    entity_type="FI_VAT",
                    start=start,
                    end=end,
                    score=0.95,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=0.95,
                        pattern_name="fi_vat_alv",
                        pattern=r"FI\d{8}",
                        validation_result=True,
                    ),
                )
            )
        return results
