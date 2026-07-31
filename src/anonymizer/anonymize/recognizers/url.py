"""URL / webpage link recognizer (scheme and www. forms)."""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# http(s)://..., bare www...., and multi-label hosts (a.b.fi)
# Avoid trailing punctuation commonly stuck to links.
# Do NOT match two-label name.xx (christofer.sj) — email FP source.
_URL_RE = re.compile(
    r"(?i)"
    r"(?<![\w@])"
    r"("
    r"(?:https?|ftp)://[^\s<>\"')\]]+"
    r"|"
    r"www\.[^\s<>\"')\]]+"
    r"|"
    r"[a-z0-9][a-z0-9\-]*\.[a-z0-9][a-z0-9\-]*\.[a-z]{2,24}"
    r"(?:/[^\s<>\"')\]]*)?"
    r")"
)

_TRAIL_PUNCT = ".,;:!?)]}'\""


def _trim_url(match: str) -> str:
    url = match
    while url and url[-1] in _TRAIL_PUNCT:
        url = url[:-1]
    return url


def find_urls(text: str) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []
    for m in _URL_RE.finditer(text):
        raw = m.group(1)
        trimmed = _trim_url(raw)
        if len(trimmed) < 5:
            continue
        # Drop email-like leftovers
        if "@" in trimmed and "://" not in trimmed and not trimmed.lower().startswith(
            "www."
        ):
            continue
        end = m.start(1) + len(trimmed)
        hits.append((m.start(1), end, trimmed))
    return hits


class WebUrlRecognizer(EntityRecognizer):
    """Detect webpage links as URL entities."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["URL"],
            supported_language="en",
            name="WebUrlRecognizer",
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
        if entities and "URL" not in entities:
            return []
        results: list[RecognizerResult] = []
        for start, end, _ in find_urls(text):
            results.append(
                RecognizerResult(
                    entity_type="URL",
                    start=start,
                    end=end,
                    score=0.9,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=0.9,
                        pattern_name="url",
                        pattern="http(s)|www",
                        validation_result=True,
                    ),
                )
            )
        return results
