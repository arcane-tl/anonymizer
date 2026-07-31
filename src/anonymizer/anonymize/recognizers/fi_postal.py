"""Finnish postal code (postinumero) recognizer.

Finnish postcodes are exactly five digits (e.g. 02330, 00100).

Context rules (reduce false positives):
- Precisely 5 digits — never a substring of a longer digit run.
- Leading: whitespace, ``:`` (field form ``Postal code:02330``), or line start.
- Trailing: **only** whitespace or comma ``,`` (or end of string/line).
  Not a period — avoids money/decimals like ``12345.00`` → ``[POSTAL].00``.
"""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# Leading: space, colon, line start
# Trailing: space/comma (usual), sentence '.' not followed by digit, or EOS
# Never '.' + digit (decimals like 12345.00 → false [POSTAL].00)
_POSTAL_RE = re.compile(
    r"(?:"
    r"(?<=\s)"
    r"|"
    r"(?<=:)"
    r"|"
    r"^"
    r")"
    r"(\d{5})"
    r"(?="
    r"[\s,]"  # usual: space before city, or comma
    r"|"
    r"\.(?!\d)"  # end of sentence, not money decimal
    r"|"
    r"$"
    r")",
    re.MULTILINE,
)


def is_plausible_fi_postal(code: str) -> bool:
    if len(code) != 5 or not code.isdigit():
        return False
    # Finnish postcodes 00100–99999; 00000–00099 unused
    return int(code) >= 100


_NON_POSTAL_CONTEXT = re.compile(
    r"(?i)(kilometri|k\s*/\s*m|käyttöaika|mittari|raja|tunnit|km\b)",
    re.UNICODE,
)


def find_fi_postals(text: str) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []
    for m in _POSTAL_RE.finditer(text):
        code = m.group(1)
        if not is_plausible_fi_postal(code):
            continue
        start, end = m.start(1), m.end(1)
        if start > 0 and text[start - 1].isdigit():
            continue
        if end < len(text) and text[end].isdigit():
            continue
        # Explicit reject: five digits that are the integer part of a decimal
        if end + 1 < len(text) and text[end] == "." and text[end + 1].isdigit():
            continue
        # Usage limits etc. (e.g. Kilometri/käyttöaikaraja: 23333)
        window = text[max(0, start - 48) : start]
        if _NON_POSTAL_CONTEXT.search(window):
            continue
        hits.append((start, end, code))
    return hits


class FiPostalCodeRecognizer(EntityRecognizer):
    """Detect Finnish 5-digit postal codes (space/comma after only)."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["FI_POSTAL_CODE"],
            supported_language="en",
            name="FiPostalCodeRecognizer",
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
        if entities and "FI_POSTAL_CODE" not in entities:
            return []
        results: list[RecognizerResult] = []
        for start, end, _ in find_fi_postals(text):
            results.append(
                RecognizerResult(
                    entity_type="FI_POSTAL_CODE",
                    start=start,
                    end=end,
                    score=0.9,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=0.9,
                        pattern_name="fi_postal",
                        pattern=r"(space|:)NNNNN(space|,|$)",
                        validation_result=True,
                    ),
                )
            )
        return results
