"""Finnish business ID (Y-tunnus) recognizer."""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult, AnalysisExplanation
from presidio_analyzer.nlp_engine import NlpArtifacts

# 1234567-8  (7 digits, hyphen, check digit)
_YTUNNUS_RE = re.compile(r"\b(\d{7})-(\d)\b")

_WEIGHTS = [7, 9, 10, 5, 8, 4, 2]


def is_valid_y_tunnus(number7: str, check: str) -> bool:
    if len(number7) != 7 or not number7.isdigit() or not check.isdigit():
        return False
    total = sum(int(d) * w for d, w in zip(number7, _WEIGHTS, strict=True))
    rem = total % 11
    if rem == 0:
        expected = 0
    elif rem == 1:
        return False  # invalid
    else:
        expected = 11 - rem
    return int(check) == expected


class FiBusinessIdRecognizer(EntityRecognizer):
    """Detect Finnish Y-tunnus with checksum validation."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["FI_BUSINESS_ID"],
            supported_language="en",
            name="FiBusinessIdRecognizer",
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
        if entities and "FI_BUSINESS_ID" not in entities:
            return []
        results: list[RecognizerResult] = []
        for m in _YTUNNUS_RE.finditer(text):
            num, chk = m.group(1), m.group(2)
            if not is_valid_y_tunnus(num, chk):
                continue
            results.append(
                RecognizerResult(
                    entity_type="FI_BUSINESS_ID",
                    start=m.start(),
                    end=m.end(),
                    score=0.9,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=0.9,
                        pattern_name="fi_y_tunnus",
                        pattern=str(_YTUNNUS_RE.pattern),
                        validation_result=True,
                    ),
                )
            )
        return results
