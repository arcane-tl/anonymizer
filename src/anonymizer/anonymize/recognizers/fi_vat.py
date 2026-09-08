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

_VAT_LABEL_RE = re.compile(
    r"(?i)\b(?:"
    r"alv(?:[\s\-]?tunnus|[\s\-]?numero|[\s\-]?nro)?|"
    r"vat(?:[\s\-]?id|[\s\-]?number|[\s\-]?no\.?)?|"
    r"fi[\s\-]?alv|arvonlisävero(?:tunnus)?"
    r")\b",
)
_LABEL_LOOKBACK = 48


def is_valid_fi_vat(digits8: str) -> bool:
    if len(digits8) != 8 or not digits8.isdigit():
        return False
    return is_valid_y_tunnus(digits8[:7], digits8[7])


def _has_vat_label(text: str, start: int) -> bool:
    window = text[max(0, start - _LABEL_LOOKBACK) : start]
    return _VAT_LABEL_RE.search(window) is not None


def find_fi_vats(text: str, *, allow_labeled_invalid: bool = True) -> list[tuple[int, int, str, bool]]:
    """Return ``(start, end, surface, checksum_valid)`` for FI VAT candidates."""
    hits: list[tuple[int, int, str, bool]] = []
    for m in _VAT_RE.finditer(text):
        digits = m.group(2)
        valid = is_valid_fi_vat(digits)
        if not valid and not (
            allow_labeled_invalid and _has_vat_label(text, m.start())
        ):
            continue
        hits.append((m.start(), m.end(), m.group(0), valid))
    return hits


class FiVatRecognizer(EntityRecognizer):
    """Detect Finnish ALV / VAT numbers (FI + 8 digits with checksum).

    Invalid checksums are accepted at score 0.7 when anchored by an ALV/VAT label.
    """

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
        for start, end, _surface, valid in find_fi_vats(text):
            score = 0.95 if valid else 0.7
            results.append(
                RecognizerResult(
                    entity_type="FI_VAT",
                    start=start,
                    end=end,
                    score=score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=score,
                        pattern_name="fi_vat_alv" if valid else "fi_vat_alv_labeled",
                        pattern=r"FI\d{8}",
                        validation_result=valid,
                    ),
                )
            )
        return results
