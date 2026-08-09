"""Generic multi-pattern EntityRecognizer built from YAML (or in-memory specs)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts


@dataclass(frozen=True)
class PatternSpec:
    name: str
    regex: str
    score: float = 0.85


class PatternListRecognizer(EntityRecognizer):
    """Run one or more regexes for a single entity type (language-agnostic)."""

    def __init__(
        self,
        *,
        name: str,
        entity_type: str,
        patterns: Sequence[PatternSpec],
        supported_language: str = "en",
    ) -> None:
        if not patterns:
            raise ValueError(f"PatternListRecognizer {name!r} needs at least one pattern")
        super().__init__(
            supported_entities=[entity_type.upper()],
            supported_language=supported_language,
            name=name,
        )
        self._entity_type = entity_type.upper()
        self._compiled: list[tuple[str, re.Pattern[str], float]] = []
        for p in patterns:
            try:
                cre = re.compile(p.regex)
            except re.error as exc:
                raise ValueError(
                    f"Invalid regex in recognizer {name!r} pattern {p.name!r}: {exc}"
                ) from exc
            score = float(p.score)
            if not 0.0 < score <= 1.0:
                score = 0.85
            self._compiled.append((p.name, cre, score))

    def load(self) -> None:
        return

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: NlpArtifacts = None,  # noqa: ANN001
        regex_flags: Optional[int] = None,  # noqa: ARG002
    ) -> List[RecognizerResult]:
        if entities and self._entity_type not in entities:
            return []
        results: list[RecognizerResult] = []
        for pname, cre, score in self._compiled:
            for m in cre.finditer(text):
                # Skip zero-width
                if m.start() >= m.end():
                    continue
                results.append(
                    RecognizerResult(
                        entity_type=self._entity_type,
                        start=m.start(),
                        end=m.end(),
                        score=score,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.name,
                            original_score=score,
                            pattern_name=pname,
                            pattern=cre.pattern,
                            validation_result=True,
                        ),
                    )
                )
        return results
