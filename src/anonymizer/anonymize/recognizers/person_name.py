"""Person name patterns: Finnish 'Last, First' and labelled name fields."""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# Surname, Given (common on FI forms: Lindroos, Tomi)
_LAST_FIRST = re.compile(
    r"(?<![A-Za-zÅÄÖåäö])"
    r"([A-ZÅÄÖ][a-zåäöA-ZÅÄÖ\-']{1,40})"
    r",\s*"
    r"([A-ZÅÄÖ][a-zåäöA-ZÅÄÖ\-']{1,40})"
    r"(?![A-Za-zÅÄÖåäö])",
    re.UNICODE,
)

# After name field labels
_LABELLED = re.compile(
    r"(?i)(?:^|[\n:])\s*"
    r"(?:nimi|name|yhteyshenkilö|contact\s*person|business\s*contact)"
    r"\s*:\s*"
    r"([A-ZÅÄÖ][^\n]{2,60})",
    re.UNICODE | re.MULTILINE,
)


def _looks_like_person_pair(last: str, first: str) -> bool:
    """Reject acronyms / legal fragments mistaken for 'Last, First'."""
    # Second token ALL-CAPS short → LOI, MOU, ATP…
    if first.isupper() and len(first) <= 4:
        return False
    if last.isupper() and len(last) <= 4:
        return False
    # Legal / common non-name first tokens
    if last.casefold() in {
        "intent",
        "understanding",
        "agreement",
        "section",
        "article",
        "schedule",
        "appendix",
        "force",
        "green",
    }:
        return False
    if first.casefold() in {"intent", "understanding", "majeure", "card"}:
        return False
    return True


def find_person_names(text: str) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []
    seen: set[tuple[int, int]] = set()

    for m in _LAST_FIRST.finditer(text):
        last, first = m.group(1), m.group(2)
        if not _looks_like_person_pair(last, first):
            continue
        start, end = m.start(1), m.end(2)
        # Include comma between names
        span = (start, end)
        if span in seen:
            continue
        # Skip if looks like company (contains Oy etc.) — handled as ORG
        surface = text[start:end]
        if re.search(r"(?i)\b(oy|oyj|ab|ltd|inc)\b", surface):
            continue
        seen.add(span)
        hits.append((start, end, surface))

    for m in _LABELLED.finditer(text):
        start, end = m.start(1), m.end(1)
        surface = text[start:end].strip().rstrip(".,;")
        if len(surface) < 3:
            continue
        # Prefer Last, First full span if present inside
        inner = _LAST_FIRST.search(surface)
        if inner:
            s = start + inner.start(1)
            e = start + inner.end(2)
            span = (s, e)
            if span not in seen:
                seen.add(span)
                hits.append((s, e, text[s:e]))
            continue
        # Single or multi-word name after label
        if re.search(r"(?i)\b(oy|oyj|ab|ltd)\b", surface):
            continue
        span = (start, start + len(surface))
        if span not in seen:
            seen.add(span)
            hits.append((start, start + len(surface), surface))

    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    return hits


class PersonNameRecognizer(EntityRecognizer):
    """Detect 'Last, First' and labelled person name fields."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["PERSON"],
            supported_language="en",
            name="PersonNameRecognizer",
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
        if entities and "PERSON" not in entities:
            return []
        results: list[RecognizerResult] = []
        for start, end, _ in find_person_names(text):
            results.append(
                RecognizerResult(
                    entity_type="PERSON",
                    start=start,
                    end=end,
                    score=0.88,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=0.88,
                        pattern_name="last_first_or_label",
                        pattern="Last, First / Nimi:",
                        validation_result=True,
                    ),
                )
            )
        return results
