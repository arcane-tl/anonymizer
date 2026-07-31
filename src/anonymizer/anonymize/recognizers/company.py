"""Company names via legal-form morphology (Oy, Ltd, Inc, …).

Patterns encode *legal form suffixes*, not specific company names.
Any capitalised / ALL-CAPS name tokens before a recognised form match.
"""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# Structural legal forms only (case-insensitive via (?i:…))
_LEGAL = (
    r"(?i:"
    r"Oyj|Oy\s+Ab|Oy|Abp|Ab|Ky|"
    r"Avoin\s+yhtiö|"
    r"Ltd\.?|Limited|Inc\.?|Incorporated|Corp\.?|Corporation|"
    r"LLC|LLP|plc|GmbH|AG|SA|SAS|BV|NV|"
    r"Co\.|Company|Group|Holdings?"
    r")"
)

_NAME_TOKEN = r"[A-ZÅÄÖ][A-Za-zÅÄÖåäö0-9&'’\-]*"
# Horizontal whitespace only — do not cross newlines (avoids gluing lines)
_HSPACE = r"[ \t]+"

_COMPANY = re.compile(
    rf"(?<![A-Za-zÅÄÖåäö0-9])"
    rf"("
    rf"{_NAME_TOKEN}"
    rf"(?:{_HSPACE}(?:&|{_NAME_TOKEN})){{0,5}}"
    rf"{_HSPACE}{_LEGAL}"
    rf")"
    rf"(?![A-Za-zÅÄÖåäö0-9])",
    re.UNICODE,
)


# Role words often glued before a legal-form company name (not company catalogs).
# Matched on surface/lemma casefold — spaCy often tags these as PROPN in ALL-CAPS lines.
_ROLE_LEMMAS = {
    "client",
    "customer",
    "supplier",
    "provider",
    "vendor",
    "seller",
    "buyer",
    "contractor",
    "toimittaja",
    "tilaaja",
    "asiakas",
    "myyjä",
    "ostaja",
    "brand",
    "brands",
    "brändi",
    "brändiä",
}


def _is_role_token(tok) -> bool:
    return (
        tok.text.casefold() in _ROLE_LEMMAS
        or tok.lemma_.casefold() in _ROLE_LEMMAS
    )


def _strip_leading_function_words(text: str, start: int, end: int) -> tuple[int, int]:
    """Drop DET/ADP/role words before the company name (POS + surface role match)."""
    surface = text[start:end]
    try:
        from anonymizer.anonymize.recognizers.brand_org import _nlp_for_heuristic

        nlp = _nlp_for_heuristic()
    except Exception:
        nlp = None
    if nlp is None:
        # Regex fallback: leading role word + space
        m = re.match(
            r"(?i)^(" + "|".join(re.escape(r) for r in sorted(_ROLE_LEMMAS, key=len, reverse=True))
            + r")\s+",
            surface,
        )
        if m:
            return start + m.end(), end
        return start, end
    doc = nlp(surface)
    cut = 0
    for tok in doc:
        if tok.is_space:
            cut = tok.idx + len(tok)
            continue
        if tok.pos_ in {"DET", "ADP", "PRON", "CCONJ", "SCONJ", "ADV", "PART"}:
            cut = tok.idx + len(tok.text)
            while cut < len(surface) and surface[cut].isspace():
                cut += 1
            continue
        if tok.is_stop and tok.pos_ not in {"PROPN", "NOUN", "ADJ"}:
            cut = tok.idx + len(tok.text)
            while cut < len(surface) and surface[cut].isspace():
                cut += 1
            continue
        # "Client ACME LOGISTICS LTD" / "Toimittaja NORDIC … OY" (any POS)
        if _is_role_token(tok) and tok.i + 1 < len(doc):
            cut = tok.idx + len(tok.text)
            while cut < len(surface) and surface[cut].isspace():
                cut += 1
            continue
        break
    if 0 < cut < len(surface):
        return start + cut, end
    return start, end


def find_companies(text: str) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []
    for m in _COMPANY.finditer(text):
        start, end = m.start(1), m.end(1)
        start, end = _strip_leading_function_words(text, start, end)
        value = text[start:end].strip()
        if len(value) < 4 or len(value.split()) < 2:
            continue
        hits.append((start, end, value))
    return hits


class CompanyRecognizer(EntityRecognizer):
    """Detect *Name + legal form* as ORG (morphology only, no name list)."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["ORG"],
            supported_language="en",
            name="CompanyRecognizer",
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
        if entities and "ORG" not in entities:
            return []
        results: list[RecognizerResult] = []
        for start, end, _ in find_companies(text):
            results.append(
                RecognizerResult(
                    entity_type="ORG",
                    start=start,
                    end=end,
                    score=0.9,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=0.9,
                        pattern_name="legal_form_suffix",
                        pattern="name + Oy|Ltd|Inc|…",
                        validation_result=True,
                    ),
                )
            )
        return results
