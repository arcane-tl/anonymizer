"""Finnish personal identity code (henkilötunnus / hetu) recognizer."""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult, AnalysisExplanation
from presidio_analyzer.nlp_engine import NlpArtifacts

# ddmmyyCxxxZ  where C is century sign + - A B etc., Z check char
_HETU_RE = re.compile(
    r"\b(\d{6})([-+A-FU-Y])(\d{3})([0-9A-Y])\b",
    re.IGNORECASE,
)

_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"


def is_valid_hetu(full: str) -> bool:
    m = _HETU_RE.fullmatch(full.strip())
    if not m:
        return False
    date, century, individual, check = m.groups()
    # Basic date sanity (day/month); full calendar validation is overkill for PII
    day = int(date[0:2])
    month = int(date[2:4])
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return False
    if not (0 <= int(individual) <= 899):  # 000–899 personal; 900+ for institutions historically
        # Allow 001–899 typically; 000 invalid for persons
        pass
    n = int(date + individual)
    expected = _CHECK[n % 31]
    return check.upper() == expected


class FiHetuRecognizer(EntityRecognizer):
    """Detect Finnish henkilötunnus with checksum validation."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["FI_HETU"],
            supported_language="en",
            name="FiHetuRecognizer",
        )
        # Also register for fi context — Presidio filters by language; we add twice in engine.

    def load(self) -> None:
        return

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: NlpArtifacts = None,  # noqa: ANN001
        regex_flags: Optional[int] = None,  # noqa: ARG002
    ) -> List[RecognizerResult]:
        if entities and "FI_HETU" not in entities:
            return []
        results: list[RecognizerResult] = []
        for m in _HETU_RE.finditer(text):
            value = m.group(0)
            if not is_valid_hetu(value):
                continue
            results.append(
                RecognizerResult(
                    entity_type="FI_HETU",
                    start=m.start(),
                    end=m.end(),
                    score=0.95,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=0.95,
                        pattern_name="fi_hetu",
                        pattern=str(_HETU_RE.pattern),
                        validation_result=True,
                    ),
                )
            )
        return results
