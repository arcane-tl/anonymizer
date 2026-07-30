"""Presidio + spaCy anonymization with stable placeholders."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Iterable

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider

from anonymizer.anonymize.config import (
    SPACY_FALLBACKS,
    SPACY_MODELS,
    AnonymizerConfig,
)
from anonymizer.anonymize.language import resolve_language
from anonymizer.anonymize.mapping import EntityMap, normalize_entity_text
from anonymizer.anonymize.recognizers.fi_business_id import FiBusinessIdRecognizer
from anonymizer.anonymize.recognizers.fi_hetu import FiHetuRecognizer
from anonymizer.anonymize.recognizers.fi_phone import FiPhoneRecognizer
from anonymizer.models import AnonymizeResult, EntityHit, LanguageDecision

logger = logging.getLogger(__name__)

# spaCy label → Presidio entity type
_SPACY_LABEL_MAP = {
    "PERSON": "PERSON",
    "PER": "PERSON",
    "ORG": "ORG",
    "ORGANIZATION": "ORG",
    "LOC": "LOCATION",
    "GPE": "LOCATION",
    "LOCATION": "LOCATION",
    "FAC": "LOCATION",
    "NORP": "NRP",
}


def _resolve_spacy_model(lang: str) -> str:
    import spacy

    primary = SPACY_MODELS[lang]
    candidates = [primary, *SPACY_FALLBACKS.get(lang, [])]
    for name in candidates:
        try:
            spacy.load(name)
            return name
        except OSError:
            continue
    raise RuntimeError(
        f"No spaCy model found for language '{lang}'. Tried: {candidates}. "
        f"Install with: python -m spacy download {primary}"
    )


@lru_cache(maxsize=2)
def _pattern_analyzer() -> AnalyzerEngine:
    """
    English Presidio engine used for language-agnostic pattern recognizers
    (email, phone, IBAN, cards) plus Finnish custom ID recognizers.
    NER from this engine is used only when 'en' is in nlp_passes.
    """
    model_name = _resolve_spacy_model("en")
    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": model_name}],
    }
    provider = NlpEngineProvider(nlp_configuration=configuration)
    nlp_engine = provider.create_engine()
    registry = RecognizerRegistry(supported_languages=["en"])
    registry.load_predefined_recognizers(nlp_engine=nlp_engine, languages=["en"])
    for Rec in (FiHetuRecognizer, FiBusinessIdRecognizer, FiPhoneRecognizer):
        rec = Rec()
        rec.supported_language = "en"
        registry.add_recognizer(rec)
    return AnalyzerEngine(
        nlp_engine=nlp_engine,
        registry=registry,
        supported_languages=["en"],
    )


@lru_cache(maxsize=4)
def _spacy_nlp(lang: str):
    import spacy

    return spacy.load(_resolve_spacy_model(lang))


def _spacy_ner_results(
    text: str,
    lang: str,
    entities: list[str],
    score: float = 0.75,
) -> list[RecognizerResult]:
    try:
        nlp = _spacy_nlp(lang)
    except Exception as exc:
        logger.warning("spaCy load failed for %s: %s", lang, exc)
        return []
    # Avoid pipeline errors on empty
    if not text.strip():
        return []
    # spaCy has max length; truncate extremely long blocks with warning
    if len(text) > nlp.max_length:
        logger.warning("Text length %s exceeds spaCy max; truncating", len(text))
        text = text[: nlp.max_length]
    doc = nlp(text)
    wanted = set(entities)
    results: list[RecognizerResult] = []
    for ent in doc.ents:
        mapped = _SPACY_LABEL_MAP.get(ent.label_.upper())
        if not mapped:
            continue
        if wanted and mapped not in wanted:
            continue
        results.append(
            RecognizerResult(
                entity_type=mapped,
                start=ent.start_char,
                end=ent.end_char,
                score=score,
            )
        )
    return results


def _pattern_results(
    text: str,
    entities: list[str],
    score_threshold: float,
    include_ner: bool,
) -> list[RecognizerResult]:
    """Run Presidio (EN) for patterns; optionally include EN NER."""
    try:
        analyzer = _pattern_analyzer()
    except RuntimeError as exc:
        logger.warning("%s", exc)
        # Still run FI custom recognizers standalone
        return _standalone_fi_patterns(text, entities)

    if include_ner:
        ent_list = list(entities)
    else:
        # Pattern / structured only — exclude pure NER types to reduce noise
        ner_only = {"PERSON", "ORG", "LOCATION", "NRP"}
        ent_list = [e for e in entities if e not in ner_only]
        if not ent_list:
            return _standalone_fi_patterns(text, entities)

    try:
        found = analyzer.analyze(
            text=text,
            language="en",
            entities=ent_list,
            score_threshold=score_threshold,
        )
    except Exception as exc:
        logger.warning("Presidio pattern analyze failed: %s", exc)
        found = []

    # Ensure FI IDs even if entity filter omitted them somehow
    found.extend(_standalone_fi_patterns(text, entities))
    return found


def _standalone_fi_patterns(
    text: str, entities: list[str]
) -> list[RecognizerResult]:
    results: list[RecognizerResult] = []
    if not entities or "FI_HETU" in entities:
        results.extend(FiHetuRecognizer().analyze(text, entities=["FI_HETU"]))
    if not entities or "FI_BUSINESS_ID" in entities:
        results.extend(
            FiBusinessIdRecognizer().analyze(text, entities=["FI_BUSINESS_ID"])
        )
    if not entities or "PHONE_NUMBER" in entities:
        results.extend(
            FiPhoneRecognizer().analyze(text, entities=["PHONE_NUMBER"])
        )
    return results


def _merge_results(results: list[RecognizerResult]) -> list[RecognizerResult]:
    """Resolve overlapping spans: prefer higher score, then longer span."""
    if not results:
        return []
    ordered = sorted(results, key=lambda r: (r.start, -(r.end - r.start), -r.score))
    merged: list[RecognizerResult] = []
    for r in ordered:
        conflict = False
        for i, existing in enumerate(merged):
            if r.start < existing.end and r.end > existing.start:
                conflict = True
                r_len = r.end - r.start
                e_len = existing.end - existing.start
                if r.score > existing.score or (
                    r.score == existing.score and r_len > e_len
                ):
                    merged[i] = r
                break
        if not conflict:
            merged.append(r)
    return sorted(merged, key=lambda r: r.start)


def _denylist_hits(
    text: str,
    denylist: Iterable,
    entities: set[str],
) -> list[RecognizerResult]:
    results: list[RecognizerResult] = []
    lower = text.casefold()
    for entry in denylist:
        needle = entry.text.strip()
        if not needle:
            continue
        etype = entry.entity_type.upper()
        start = 0
        nlow = needle.casefold()
        while True:
            idx = lower.find(nlow, start)
            if idx < 0:
                break
            results.append(
                RecognizerResult(
                    entity_type=etype,
                    start=idx,
                    end=idx + len(needle),
                    score=1.0,
                )
            )
            start = idx + max(len(needle), 1)
    return results


def _allowlist_filter(
    text: str,
    results: list[RecognizerResult],
    allowlist: list[str],
) -> list[RecognizerResult]:
    if not allowlist:
        return results
    allowed = {normalize_entity_text(a) for a in allowlist if a}
    return [
        r
        for r in results
        if normalize_entity_text(text[r.start : r.end]) not in allowed
    ]


def apply_stable_placeholders(
    text: str,
    results: list[RecognizerResult],
    entity_map: EntityMap | None = None,
) -> tuple[str, EntityMap, list[EntityHit]]:
    """Replace spans with stable placeholders.

    Indices follow first appearance (left-to-right); string mutation is
    applied right-to-left so character offsets remain valid.
    """
    entity_map = entity_map or EntityMap()
    forward = sorted(results, key=lambda r: (r.start, r.end))
    planned: list[tuple[RecognizerResult, str, str]] = []
    hits: list[EntityHit] = []
    for r in forward:
        surface = text[r.start : r.end]
        placeholder = entity_map.get_or_assign(r.entity_type, surface)
        planned.append((r, surface, placeholder))
        hits.append(
            EntityHit(
                entity_type=r.entity_type,
                text=surface,
                start=r.start,
                end=r.end,
                score=r.score,
            )
        )
    chars = list(text)
    for r, _surface, placeholder in sorted(
        planned, key=lambda item: item[0].start, reverse=True
    ):
        chars[r.start : r.end] = list(placeholder)
    return "".join(chars), entity_map, hits


class DocumentAnonymizer:
    """High-level anonymizer: language routing + multi-pass analyze + stable replace."""

    def __init__(self, config: AnonymizerConfig | None = None) -> None:
        self.config = config or AnonymizerConfig()

    def analyze_text(
        self,
        text: str,
        language_decision: LanguageDecision | None = None,
        lang_flag: str | None = None,
    ) -> tuple[list[RecognizerResult], LanguageDecision]:
        flag = lang_flag if lang_flag is not None else self.config.lang
        decision = language_decision or resolve_language(flag, text)
        entities = self.config.effective_entities()
        all_results: list[RecognizerResult] = []

        # spaCy NER per selected language
        for lang in decision.nlp_passes:
            all_results.extend(_spacy_ner_results(text, lang, entities))

        # Patterns always (email, phone, IBAN, hetu, …); EN NER if en pass selected
        # EN NER already added via spaCy above — patterns without NER types
        all_results.extend(
            _pattern_results(
                text,
                entities,
                score_threshold=self.config.score_threshold,
                include_ner=False,
            )
        )

        all_results.extend(
            _denylist_hits(text, self.config.denylist, set(entities))
        )

        merged = _merge_results(all_results)
        merged = _allowlist_filter(text, merged, self.config.allowlist)
        return merged, decision

    def anonymize_text(
        self,
        text: str,
        lang_flag: str | None = None,
    ) -> AnonymizeResult:
        results, decision = self.analyze_text(text, lang_flag=lang_flag)
        anonymized, entity_map, hits = apply_stable_placeholders(text, results)
        type_counts: dict[str, int] = {}
        seen_keys: set[tuple[str, str]] = set()
        for h in hits:
            key = (h.entity_type, normalize_entity_text(h.text))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            type_counts[h.entity_type] = type_counts.get(h.entity_type, 0) + 1

        return AnonymizeResult(
            anonymized_text=anonymized,
            entity_counts=type_counts,
            mapping=dict(entity_map.reverse),
            language=decision,
            hits=hits,
        )

    def anonymize_blocks(
        self,
        blocks_text_list: list[str],
        lang_flag: str | None = None,
    ) -> tuple[list[str], AnonymizeResult]:
        """
        Anonymize each block with a shared EntityMap so placeholders are
        stable across the document. Language detection uses joined text.
        """
        joined = "\n\n".join(blocks_text_list)
        flag = lang_flag if lang_flag is not None else self.config.lang
        decision = resolve_language(flag, joined)
        entity_map = EntityMap()
        all_hits: list[EntityHit] = []
        out_blocks: list[str] = []
        type_counts: dict[str, int] = {}
        seen_keys: set[tuple[str, str]] = set()

        for block in blocks_text_list:
            if not block.strip():
                out_blocks.append(block)
                continue
            results, _ = self.analyze_text(
                block, language_decision=decision, lang_flag=flag
            )
            anon, entity_map, hits = apply_stable_placeholders(
                block, results, entity_map=entity_map
            )
            out_blocks.append(anon)
            for h in hits:
                all_hits.append(h)
                key = (h.entity_type, normalize_entity_text(h.text))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                type_counts[h.entity_type] = type_counts.get(h.entity_type, 0) + 1

        summary = AnonymizeResult(
            anonymized_text="\n\n".join(out_blocks),
            entity_counts=type_counts,
            mapping=dict(entity_map.reverse),
            language=decision,
            hits=all_hits,
        )
        return out_blocks, summary
