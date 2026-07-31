"""Vehicle Identification Number (VIN / valmistenumero) — ISO 3779 style."""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# 17 chars; letters exclude I, O, Q (ISO 3779)
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b", re.IGNORECASE)

# ISO 3779 transliteration for check digit
_TRANSLIT = {
    **{str(d): d for d in range(10)},
    **{
        c: v
        for c, v in zip(
            "ABCDEFGHJKLMNPRSTUVWXYZ",
            [1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 5, 7, 9, 2, 3, 4, 5, 6, 7, 8, 9],
        )
    },
}
_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def _check_digit_ok(vin: str) -> bool:
    vin = vin.upper()
    if len(vin) != 17:
        return False
    try:
        total = sum(_TRANSLIT[vin[i]] * _WEIGHTS[i] for i in range(17))
    except KeyError:
        return False
    rem = total % 11
    expect = "X" if rem == 10 else str(rem)
    return vin[8] == expect


def _looks_like_vin(value: str) -> bool:
    v = value.upper()
    if len(v) != 17:
        return False
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", v):
        return False
    letters = sum(1 for c in v if c.isalpha())
    digits = sum(1 for c in v if c.isdigit())
    # Real VINs mix letters and digits (reject pure serial blobs)
    if letters < 2 or digits < 2:
        return False
    return True


def find_vins(text: str) -> list[tuple[int, int, str, float]]:
    hits: list[tuple[int, int, str, float]] = []
    for m in _VIN_RE.finditer(text):
        raw = m.group(1)
        if not _looks_like_vin(raw):
            continue
        score = 0.95 if _check_digit_ok(raw) else 0.85
        # Slight boost when near valmistenumero / VIN label
        window = text[max(0, m.start() - 48) : m.start()].casefold()
        if any(
            k in window
            for k in ("valmistenumer", "vin", "chassis", "runkonumer")
        ):
            score = min(0.98, score + 0.05)
        hits.append((m.start(1), m.end(1), raw.upper(), score))
    return hits


class VehicleVinRecognizer(EntityRecognizer):
    """Detect 17-character vehicle identification numbers."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["VEHICLE_VIN"],
            supported_language="en",
            name="VehicleVinRecognizer",
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
        if entities and "VEHICLE_VIN" not in entities:
            return []
        results: list[RecognizerResult] = []
        for start, end, _value, score in find_vins(text):
            results.append(
                RecognizerResult(
                    entity_type="VEHICLE_VIN",
                    start=start,
                    end=end,
                    score=score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=score,
                        pattern_name="iso3779_vin",
                        pattern="17-char VIN",
                        validation_result=True,
                    ),
                )
            )
        return results
