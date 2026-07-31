"""Finnish phone number recognizer."""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# Digit count bounds on the raw match (after stripping non-digits).
# National with trunk 0: ~9–11. International +358: ~11–13. 00358…: ~13–15.
_MIN_DIGITS = 8
_MAX_DIGITS = 15

# +358 / 00358 international forms (optional (0) after country code)
_INTL = re.compile(
    r"(?<!\w)"
    r"(?:"
    r"\+358|00358"
    r")"
    r"[\s\-./]*"
    r"\(?\s*0?\s*\)?"
    r"[\s\-./]*"
    r"\d(?:[\s\-./()]*\d){6,12}"
    r"(?!\d)",
    re.IGNORECASE,
)

# Shared national trunk+prefix (mobile / area) without outer parens
_NAT_PREFIX = (
    r"(?:"
    r"4\d|50|45|44|40|41|42|43|46|49|"  # mobile-ish
    r"9|2|3|5|6|8|13|14|15|16|17|18|19"  # area codes (partial)
    r")"
)

# National numbers with separators (prefer spaced form to avoid Y-tunnus / dates)
# e.g. 040 123 4567, 09 1234 567, 050-987-6543
_NAT_SEP = re.compile(
    rf"(?<!\d)"
    rf"0{_NAT_PREFIX}"
    rf"(?:[\s\-./]+\d{{2,4}}){{1,4}}"
    rf"(?!\d)",
)

# Parenthetical trunk+prefix: (040) 123 4567, (09) 1234 567 — common in FI print
_NAT_PAREN = re.compile(
    rf"(?<!\d)"
    rf"\(\s*0{_NAT_PREFIX}\s*\)"
    rf"(?:[\s\-./\u00a0]+\d{{2,4}}){{1,4}}"
    rf"(?!\d)",
)

# Continuous after paren: (040)1234567
_NAT_PAREN_CONT = re.compile(
    rf"(?<!\d)"
    rf"\(\s*0{_NAT_PREFIX}\s*\)"
    rf"\d{{6,8}}"
    rf"(?!\d)",
)

# Continuous national mobile (10 digits common): 0401234567, 0501234567
_NAT_MOBILE_CONT = re.compile(
    r"(?<!\d)"
    r"(?:040|041|042|043|044|045|046|049|050)"
    r"\d{6,7}"
    r"(?!\d)",
)

# Continuous landline Helsinki-style 09xxxxxxx (9–10 digits total with 0)
_NAT_LAND_CONT = re.compile(
    r"(?<!\d)"
    r"09\d{7,8}"
    r"(?!\d)",
)

# Service / corporate national: 010…, 020…, 029…, 075… (continuous)
_NAT_SERVICE_CONT = re.compile(
    r"(?<!\d)"
    r"0"
    r"(?:10|20|29|30|39|60|70|75|800|900)"
    r"\d{5,8}"
    r"(?!\d)",
)

# Same with separators: 010 832 4500
_NAT_SERVICE_SEP = re.compile(
    r"(?<!\d)"
    r"0"
    r"(?:10|20|29|30|39|60|70|75)"
    r"(?:[\s\-./\u00a0]+\d{2,4}){1,4}"
    r"(?!\d)",
)

# Service with parentheses: (010) 832 4500
_NAT_SERVICE_PAREN = re.compile(
    r"(?<!\d)"
    r"\(\s*0(?:10|20|29|30|39|60|70|75)\s*\)"
    r"(?:[\s\-./\u00a0]+\d{2,4}){1,4}"
    r"(?!\d)",
)

# After an explicit phone label, accept broader digit runs (PDF often drops
# trunk 0 or uses NBSP): e.g. Puhelinnumero: 108324500
_LABELED = re.compile(
    r"(?i)(?:puhelinnumero|puhelin|phone|tel\.?|puh\.?)\s*[:：]?\s*"
    r"("
    r"\+?358[\s\-./\u00a0()]*\d(?:[\s\-./\u00a0()]*\d){6,12}"
    r"|"
    r"0?\d(?:[\s\-./\u00a0()]*\d){6,12}"
    r")"
    r"(?!\d)",
)

_PATTERNS = (
    _INTL,
    _NAT_PAREN,
    _NAT_PAREN_CONT,
    _NAT_SERVICE_PAREN,
    _NAT_SEP,
    _NAT_MOBILE_CONT,
    _NAT_LAND_CONT,
    _NAT_SERVICE_CONT,
    _NAT_SERVICE_SEP,
)


def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)


def _normalize_phone_text(text: str) -> str:
    """NBSP / narrow spaces → regular space for matching."""
    return (
        text.replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace("\u2009", " ")
    )


def is_plausible_fi_phone(raw: str, *, labeled: bool = False) -> bool:
    """Heuristic validation for Finnish phone candidates."""
    d = _digits_only(raw)
    if not (_MIN_DIGITS <= len(d) <= _MAX_DIGITS):
        return False
    # Normalize international prefixes → national significant digits (no trunk 0)
    if d.startswith("00358"):
        national = d[5:]
    elif d.startswith("358"):
        national = d[3:]
    elif d.startswith("0"):
        national = d[1:]
    elif labeled and len(d) >= 8:
        # PDF forms sometimes omit trunk 0 after "Puhelinnumero:"
        national = d
    else:
        return False
    if national.startswith("0"):
        national = national[1:]
    # Finnish subscriber numbers are typically 7–10 digits after trunk/country
    return 7 <= len(national) <= 10


def find_fi_phones(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, matched_text) for Finnish phone numbers.

    Offsets refer to the original ``text`` (NBSP normalized only for matching
    when lengths match; we normalize in place so indices align).
    """
    # In-place compatible normalize: replace NBSP with space (same length)
    norm = _normalize_phone_text(text)
    hits: list[tuple[int, int, str]] = []
    seen: set[tuple[int, int]] = set()
    for pattern in _PATTERNS:
        for m in pattern.finditer(norm):
            span = (m.start(), m.end())
            if span in seen:
                continue
            value = text[m.start() : m.end()]  # original slice
            if not is_plausible_fi_phone(value):
                continue
            # Reject if this is clearly a Y-tunnus (7digits-1digit) already handled elsewhere
            if re.fullmatch(r"\d{7}-\d", value.strip()):
                continue
            seen.add(span)
            hits.append((m.start(), m.end(), value))
    # Label-anchored matches (group 1 = number only)
    for m in _LABELED.finditer(norm):
        start, end = m.start(1), m.end(1)
        span = (start, end)
        if span in seen:
            continue
        value = text[start:end]
        if not is_plausible_fi_phone(value, labeled=True):
            continue
        if re.fullmatch(r"\d{7}-\d", value.strip()):
            continue
        seen.add(span)
        hits.append((start, end, value))
    # Prefer longer spans on overlap
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    merged: list[tuple[int, int, str]] = []
    for start, end, value in hits:
        if merged and start < merged[-1][1]:
            # overlap: keep longer
            if end - start > merged[-1][1] - merged[-1][0]:
                merged[-1] = (start, end, value)
            continue
        merged.append((start, end, value))
    return merged


class FiPhoneRecognizer(EntityRecognizer):
    """Detect Finnish phone numbers as PHONE_NUMBER entities."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["PHONE_NUMBER"],
            supported_language="en",
            name="FiPhoneRecognizer",
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
        if entities and "PHONE_NUMBER" not in entities:
            return []
        results: list[RecognizerResult] = []
        for start, end, _value in find_fi_phones(text):
            results.append(
                RecognizerResult(
                    entity_type="PHONE_NUMBER",
                    start=start,
                    end=end,
                    score=0.9,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=0.9,
                        pattern_name="fi_phone",
                        pattern="finnish_phone",
                        validation_result=True,
                    ),
                )
            )
        return results
