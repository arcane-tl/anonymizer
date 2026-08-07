"""Presidio + spaCy anonymization with stable placeholders."""

from __future__ import annotations

import logging
import re
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
from anonymizer.anonymize.org_stems import (
    collect_stems_from_results,
    expand_org_stems_in_text,
)
from anonymizer.anonymize.recognizers.brand_org import BrandOrgRecognizer
from anonymizer.anonymize.recognizers.company import CompanyRecognizer
from anonymizer.anonymize.recognizers.fi_business_id import FiBusinessIdRecognizer
from anonymizer.anonymize.recognizers.fi_hetu import FiHetuRecognizer
from anonymizer.anonymize.recognizers.fi_phone import FiPhoneRecognizer
from anonymizer.anonymize.recognizers.fi_plate import FiPlateRecognizer
from anonymizer.anonymize.recognizers.fi_postal import FiPostalCodeRecognizer
from anonymizer.anonymize.recognizers.fi_vat import FiVatRecognizer
from anonymizer.anonymize.recognizers.person_name import PersonNameRecognizer
from anonymizer.anonymize.recognizers.street import StreetRecognizer
from anonymizer.anonymize.recognizers.url import WebUrlRecognizer
from anonymizer.anonymize.recognizers.vin import VehicleVinRecognizer
from anonymizer.extract.text_repair import is_real_web_url, repair_text_artifacts
from anonymizer.models import AnonymizeResult, EntityHit, LanguageDecision

logger = logging.getLogger(__name__)

# spaCy label → Presidio entity type
_SPACY_LABEL_MAP = {
    "PERSON": "PERSON",
    "PER": "PERSON",
    "ORG": "ORG",
    "ORGANIZATION": "ORG",
    # Brands / products often tagged PRODUCT by Finnish models
    "PRODUCT": "ORG",
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
    for Rec in (
        FiHetuRecognizer,
        FiBusinessIdRecognizer,
        FiPhoneRecognizer,
        FiPlateRecognizer,
        FiPostalCodeRecognizer,
        WebUrlRecognizer,
        StreetRecognizer,
        CompanyRecognizer,
        BrandOrgRecognizer,
    ):
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


# Contract role words often glued onto company names by NER (surface match only).
_ORG_ROLE_PREFIXES = frozenset(
    {
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
)

_LEGAL_FORM_RE = re.compile(
    r"(?i)\b(oyj|oy|abp|ab|ky|ltd|limited|inc|corp|llc|llp|gmbh|plc)\b"
)


def _trim_spacy_org_span_with_doc(doc, start: int, end: int) -> tuple[int, int]:
    """Drop leading function-word / role tokens from an ORG span."""
    # Tokens that overlap [start, end)
    span_tokens = [t for t in doc if t.idx < end and t.idx + len(t) > start]
    if len(span_tokens) < 2:
        return start, end
    i = 0
    while i < len(span_tokens) - 1:
        tok = span_tokens[i]
        if tok.is_space or tok.is_punct:
            i += 1
            continue
        if tok.pos_ in {
            "DET",
            "ADP",
            "VERB",
            "AUX",
            "PART",
            "SCONJ",
            "CCONJ",
            "ADV",
            "PRON",
            "INTJ",
        }:
            i += 1
            continue
        if tok.is_stop and tok.pos_ not in {"PROPN", "NOUN", "ADJ"}:
            i += 1
            continue
        # "Client ACME …", "Toimittaja NORDIC …" — surface role, any POS
        if tok.text.casefold() in _ORG_ROLE_PREFIXES:
            i += 1
            continue
        break
    if i == 0:
        return start, end
    new_start = span_tokens[i].idx
    if new_start >= end:
        return start, end
    return new_start, end


_DOC_TITLE_TAILS = frozenset(
    {
        "agreement",
        "contract",
        "policy",
        "addendum",
        "amendment",
        "schedule",
        "appendix",
        "annex",
        "caselist",
        "summaries",
        "ehdot",
        "peruutusehdot",
        "veloitus",
        "veloitusukset",
        "palvelut",
        "yhteensä",
        "majeure",
        "card",
        "cardiin",
    }
)

# Contract party role words (not organisations)
_CONTRACT_ROLES = frozenset(
    {
        "asiakas",
        "myyjä",
        "ostaja",
        "toimittaja",
        "tilaaja",
        "vuokralainen",
        "vuokranantaja",
        "osapuoli",
        "client",
        "customer",
        "seller",
        "buyer",
        "supplier",
        "provider",
        "author",
        "publisher",
        "lessor",
        "lessee",
    }
)

# Legal / insurance collocations (not orgs)
_LEGAL_PHRASES = frozenset(
    {
        "force majeure",
        "green card",
        "green cardiin",
        "letter of intent",
        "memorandum of understanding",
    }
)

_COMMERCIAL_LOC_SUFFIX = re.compile(
    r"(?i)(veloitus|maksu|palkkio|vuokra|ehdot|palvelut|yhteens[aä]|raja)$",
    re.UNICODE,
)


def _is_contract_role_surface(surface: str) -> bool:
    s = surface.strip().strip("\"'()«»")
    return s.casefold() in _CONTRACT_ROLES


def _is_all_caps_section_header(surface: str) -> bool:
    """Multi-word ALL-CAPS titles without legal form → section headers, not ORG.

    Keeps 2-token brands (SILVER PINE, COPPER LAKE); drops 3+ token headers and
    titles with joiners (JA/AND) or commercial legalish tokens.
    """
    s = surface.strip()
    if _LEGAL_FORM_RE.search(s):
        return False
    tokens = s.split()
    if len(tokens) < 2:
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 6:
        return False
    upper = sum(1 for c in letters if c.isupper())
    if upper / len(letters) < 0.9:
        return False
    joiners = {"ja", "and", "of", "tai", "se", "the", "for", "to", "-"}
    low = [t.casefold().strip(".,;:-") for t in tokens]
    if len(tokens) >= 3 or any(t in joiners for t in low):
        return True
    if any(t in _DOC_TITLE_TAILS for t in low):
        return True
    return False


def _looks_like_legal_boilerplate_org(nlp, surface: str) -> bool:
    """True for dictionary legal phrases mis-tagged as ORG (no legal-form suffix)."""
    if _LEGAL_FORM_RE.search(surface):
        return False
    surface = surface.strip()
    if not surface or "\n" in surface:
        return True
    if _is_contract_role_surface(surface):
        return True
    if surface.casefold() in _LEGAL_PHRASES:
        return True
    if _is_all_caps_section_header(surface):
        return True
    # Tiny ALL-CAPS acronyms (PDF, MOU, LOI, ATP) — not reliable ORG alone
    if surface.isupper() and 2 <= len(surface) <= 4 and " " not in surface:
        return True
    tokens = surface.split()
    if tokens and tokens[-1].casefold().strip(".,;:'\"") in _DOC_TITLE_TAILS:
        return True
    # "Virheellinen Leasingkohde" style section titles
    if re.search(r"(?i)\b(leasingkohde|sopimus|sopimusehdot)\b", surface):
        if not _LEGAL_FORM_RE.search(surface):
            return True
    # Geo compounds ("England and Wales") — LOCATION/GPE, not ORG
    if re.search(r"(?i)\band\b", surface):
        try:
            geo = nlp(surface)
            if any(e.label_.upper() in {"GPE", "LOC", "LOCATION"} for e in geo.ents):
                return True
        except Exception:
            pass
    try:
        probe = nlp(surface.casefold())
    except Exception:
        return False
    content = [t for t in probe if not t.is_space and not t.is_punct]
    if not content:
        return True
    # "letter of intent", "initial delivery date", "basics of contract law"
    if all(t.pos_ in {"NOUN", "ADJ", "ADP", "DET", "CCONJ", "VERB", "ADV"} for t in content):
        if not any(e.label_.upper() in {"ORG", "PRODUCT"} for e in probe.ents):
            return True
    # "X of Y" collocations with only common words
    if re.search(r"(?i)\bof\b", surface) and not any(
        e.label_.upper() in {"ORG", "PRODUCT"} for e in probe.ents
    ):
        if all(not t.is_oov for t in content):
            return True
    return False


def _looks_like_false_location(surface: str) -> bool:
    """Commercial field names mis-tagged as LOCATION/CITY."""
    s = surface.strip()
    if not s:
        return True
    if _COMMERCIAL_LOC_SUFFIX.search(s):
        return True
    if len(s) > 18 and " " not in s and "-" not in s and s[0].isupper():
        # Long single-token compounds (Ylikilometriveloitus)
        if re.search(r"(?i)(veloitus|maksu|palkkio|raja|kilometri)", s):
            return True
    return False


def _looks_like_false_person(nlp, surface: str, span_toks) -> bool:
    """Drop capitalised common nouns / lowercase fragments mis-tagged as PERSON."""
    surface = surface.strip()
    if not surface:
        return True
    # Formal names are capitalised; "lien" mid-clause is not a name
    if surface == surface.casefold():
        return True
    if len(span_toks) != 1:
        return False
    try:
        probe = nlp(surface.casefold())
    except Exception:
        return False
    if not probe:
        return False
    # "manuscript" → NOUN; real given names stay PERSON/PROPN when lowercased
    t0 = next((t for t in probe if not t.is_space and not t.is_punct), None)
    if t0 is None:
        return True
    if t0.pos_ in {"NOUN", "VERB", "ADJ", "ADV"} and not any(
        e.label_.upper() in {"PERSON", "PER"} for e in probe.ents
    ):
        return True
    return False


def _spacy_ner_results(
    text: str,
    lang: str,
    entities: list[str],
    score: float = 0.75,
) -> list[RecognizerResult]:
    """Neural NER layer (spaCy). No hard-coded entity catalogs."""
    try:
        nlp = _spacy_nlp(lang)
    except Exception as exc:
        logger.warning("spaCy load failed for %s: %s", lang, exc)
        return []
    if not text.strip():
        return []
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
        start, end = ent.start_char, ent.end_char
        surface = text[start:end]
        # Clip multi-line NER spans to the first line (spaCy often glues
        # "Jordan Avery Blake\n- Email" into one PERSON).
        if "\n" in surface or "\r" in surface:
            first = re.split(r"[\r\n]+", surface, maxsplit=1)[0].rstrip(" \t-–—:;")
            if not first.strip():
                continue
            end = start + len(first)
            surface = text[start:end]
            if not surface.strip():
                continue
        span_toks = [
            t
            for t in doc
            if t.idx >= start and t.idx < end and not t.is_space and not t.is_punct
        ]
        if mapped == "ORG":
            start, end = _trim_spacy_org_span_with_doc(doc, start, end)
            if start >= end or not text[start:end].strip():
                continue
            surface = text[start:end]
            if "\n" in surface or "\r" in surface:
                continue
            span_toks = [
                t
                for t in doc
                if t.idx >= start and t.idx < end and not t.is_space and not t.is_punct
            ]
            # Drop weak single-token common nouns tagged ORG ("Work", "PDF")
            if len(span_toks) == 1 and span_toks[0].pos_ in {
                "NOUN",
                "ADJ",
                "VERB",
                "SCONJ",
                "X",
            }:
                continue
            # Multi-token ORG without any PROPN and without legal form → boilerplate
            if span_toks and not any(t.pos_ == "PROPN" for t in span_toks):
                if not _LEGAL_FORM_RE.search(surface):
                    continue
            if _looks_like_legal_boilerplate_org(nlp, surface):
                continue
        if mapped in {"LOCATION", "CITY"}:
            if _looks_like_false_location(surface):
                continue
        if mapped == "PERSON":
            # Real person names almost always include a PROPN token
            if span_toks and not any(t.pos_ == "PROPN" for t in span_toks):
                continue
            if len(span_toks) == 1 and span_toks[0].pos_ in {"NOUN", "ADJ", "VERB"}:
                continue
            if _looks_like_false_person(nlp, surface, span_toks):
                continue
            if _is_contract_role_surface(surface):
                continue
        results.append(
            RecognizerResult(
                entity_type=mapped,
                start=start,
                end=end,
                score=score,
            )
        )
    return results


# Presidio's context-free international phones often score ~0.4; default
# score_threshold is 0.5, which silently drops unlabeled +1 / +44 numbers.
_PHONE_LOW_CONFIDENCE_FLOOR = 0.4


def _is_y_tunnus_like_phone_fp(surface: str) -> bool:
    """Y-tunnus ``1234567-8`` is a common Presidio PHONE false positive."""
    return bool(re.fullmatch(r"\d{7}-\d", surface.strip()))


def _looks_like_international_phone(surface: str) -> bool:
    """Shape check for low-confidence Presidio PHONE hits (not FI-national)."""
    s = surface.strip()
    if not s or _is_y_tunnus_like_phone_fp(s):
        return False
    # Date-like runs: 2025-01-01-11
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return False
    digits = re.sub(r"\D", "", s)
    if not (10 <= len(digits) <= 15):
        return False
    if s.startswith("+"):
        return True
    # National-style with separators: (415) 555-0199
    if re.search(r"[\s\-()./]", s):
        return True
    return False


def _keep_pattern_result(
    r: RecognizerResult,
    text: str,
    score_threshold: float,
) -> bool:
    """Filter Presidio hits; allow validated low-score international phones."""
    if r.entity_type == "URL":
        return is_real_web_url(text[r.start : r.end])
    if r.entity_type != "PHONE_NUMBER":
        return r.score >= score_threshold
    surface = text[r.start : r.end]
    if _is_y_tunnus_like_phone_fp(surface):
        return False
    if r.score >= score_threshold:
        return True
    # Low-confidence band: only keep plausible international-style numbers
    return (
        r.score >= _PHONE_LOW_CONFIDENCE_FLOOR
        and _looks_like_international_phone(surface)
    )


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
        # Still run custom pattern recognizers standalone
        return _standalone_pattern_recognizers(text, entities)

    if include_ner:
        ent_list = list(entities)
    else:
        # Pattern / structured only — do NOT run Presidio's English SpacyRecognizer
        # for PERSON/ORG/LOCATION (it mis-tags Finnish form labels like
        # "Rekisterinumero"). Those come from language-specific spaCy passes +
        # our street/company/brand heuristics.
        ner_types = {"PERSON", "ORG", "LOCATION", "NRP", "DATE_TIME"}
        ent_list = [e for e in entities if e not in ner_types]
        if not ent_list:
            return _standalone_pattern_recognizers(text, entities)

    # Pull phones slightly below the default threshold so unlabeled
    # international numbers are not dropped; non-phone types are re-filtered.
    analyze_threshold = score_threshold
    if "PHONE_NUMBER" in ent_list:
        analyze_threshold = min(score_threshold, _PHONE_LOW_CONFIDENCE_FLOOR)

    try:
        found = analyzer.analyze(
            text=text,
            language="en",
            entities=ent_list,
            score_threshold=analyze_threshold,
        )
    except Exception as exc:
        logger.warning("Presidio pattern analyze failed: %s", exc)
        found = []

    found = [r for r in found if _keep_pattern_result(r, text, score_threshold)]

    # Always run custom patterns (FI IDs, plates, URLs, streets, company suffixes)
    found.extend(_standalone_pattern_recognizers(text, entities))
    return found


def _standalone_pattern_recognizers(
    text: str, entities: list[str]
) -> list[RecognizerResult]:
    """Custom regex/suffix recognizers that must run for every document."""
    results: list[RecognizerResult] = []
    specs: list[tuple[type, list[str]]] = [
        (FiHetuRecognizer, ["FI_HETU"]),
        (FiBusinessIdRecognizer, ["FI_BUSINESS_ID"]),
        (FiVatRecognizer, ["FI_VAT"]),
        (FiPhoneRecognizer, ["PHONE_NUMBER"]),
        (FiPlateRecognizer, ["FI_LICENSE_PLATE"]),
        (FiPostalCodeRecognizer, ["FI_POSTAL_CODE"]),
        (WebUrlRecognizer, ["URL"]),
        (VehicleVinRecognizer, ["VEHICLE_VIN"]),
        (
            StreetRecognizer,
            ["STREET", "CITY", "FI_POSTAL_CODE", "LOCATION"],
        ),
        (CompanyRecognizer, ["ORG"]),
        (BrandOrgRecognizer, ["ORG"]),
        (PersonNameRecognizer, ["PERSON"]),
    ]
    for Rec, ents in specs:
        if entities and not any(e in entities for e in ents):
            continue
        # Pass full entity filter so StreetRecognizer can emit STREET/CITY/POSTAL
        results.extend(Rec().analyze(text, entities=entities or ents))
    return results


# Structured address types beat residual LOCATION on ties
_ENTITY_PRIORITY = {
    "STREET": 3,
    "CITY": 3,
    "FI_POSTAL_CODE": 3,
    "FI_LICENSE_PLATE": 3,
    "FI_HETU": 3,
    "FI_BUSINESS_ID": 3,
    "FI_VAT": 3,
    "EMAIL_ADDRESS": 3,
    "PHONE_NUMBER": 3,
    "URL": 3,
    "IBAN_CODE": 3,
    "VEHICLE_VIN": 3,
    "PERSON": 2,
    "ORG": 2,
    "LOCATION": 1,
}


def _merge_results(results: list[RecognizerResult]) -> list[RecognizerResult]:
    """Resolve overlapping spans: higher score, then type priority, then longer."""
    if not results:
        return []

    def sort_key(r: RecognizerResult):
        return (
            r.start,
            -(r.end - r.start),
            -r.score,
            -_ENTITY_PRIORITY.get(r.entity_type, 0),
        )

    ordered = sorted(results, key=sort_key)
    merged: list[RecognizerResult] = []
    for r in ordered:
        conflict = False
        for i, existing in enumerate(merged):
            if r.start < existing.end and r.end > existing.start:
                conflict = True
                r_len = r.end - r.start
                e_len = existing.end - existing.start
                r_pri = _ENTITY_PRIORITY.get(r.entity_type, 0)
                e_pri = _ENTITY_PRIORITY.get(existing.entity_type, 0)
                replace = False
                if r.score > existing.score:
                    replace = True
                elif r.score == existing.score:
                    if r_pri > e_pri:
                        replace = True
                    elif r_pri == e_pri and r_len > e_len:
                        replace = True
                elif r_pri > e_pri and r.score >= existing.score - 0.15:
                    # Structured STREET/CITY/POSTAL over slightly higher LOCATION
                    replace = True
                if replace:
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


# Morphological cue for form-field labels (not a place/person catalog)
_LABEL_TAIL = re.compile(
    r"(?i)(numero|tunniste|tunnus|osoite|koodi|kenttä|field|label|code)$"
)


_LEGAL_FORM_TOKEN = re.compile(
    r"(?i)\b(oyj|oy|abp|ab|ky|ltd|limited|inc|corp|llc|llp|plc|gmbh)\b"
)


def _looks_like_field_label(text: str, start: int, end: int) -> bool:
    """True for form labels such as 'Rekisterinumero/tunniste:' or 'Osoite:'.

    Heuristic only — does not drop real names/companies that happen to sit
    before a colon (e.g. signature lines 'NORDIC WIDGETS OY: ____').
    """
    surface = text[start:end].strip()
    if not surface or len(surface) > 80:
        return False
    # Companies with legal forms are never treated as field labels
    if _LEGAL_FORM_TOKEN.search(surface):
        return False
    rest = text[end : end + 24]
    followed_by_sep = bool(re.match(r"\s*[/：:]", rest)) or surface.endswith(":")
    # "Rekisterinumero/tunniste" style
    if "/" in surface and _LABEL_TAIL.search(surface.split("/")[-1].strip()):
        return True
    # Label morphology + separator: "Rekisterinumero:", "Postinumero:"
    if _LABEL_TAIL.search(surface) and (
        followed_by_sep or re.match(r"\s*(\n|$)", rest)
    ):
        return True
    # Single-token label before colon/slash: "Osoite:"
    if followed_by_sep and len(surface.split()) == 1:
        return True
    return False


def _filter_field_labels(
    text: str, results: list[RecognizerResult]
) -> list[RecognizerResult]:
    """Drop LOCATION/ORG/PERSON hits that are clearly form field labels."""
    kept: list[RecognizerResult] = []
    for r in results:
        if r.entity_type in {
            "LOCATION",
            "STREET",
            "CITY",
            "ORG",
            "PERSON",
        } and _looks_like_field_label(text, r.start, r.end):
            continue
        kept.append(r)
    return kept


def _drop_noisy_surfaces(
    text: str, results: list[RecognizerResult]
) -> list[RecognizerResult]:
    """Drop spans that cross newlines or are empty after strip (parse noise)."""
    kept: list[RecognizerResult] = []
    for r in results:
        if r.end <= r.start or r.start < 0 or r.end > len(text):
            continue
        surface = text[r.start : r.end]
        if "\n" in surface or "\r" in surface:
            continue
        if not surface.strip():
            continue
        kept.append(r)
    return kept


def _filter_false_org_location(
    text: str, results: list[RecognizerResult]
) -> list[RecognizerResult]:
    """Drop role words, ALL-CAPS headers, commercial LOCATION/CITY, etc."""
    kept: list[RecognizerResult] = []
    for r in results:
        surface = text[r.start : r.end]
        if r.entity_type == "ORG":
            if _is_contract_role_surface(surface):
                continue
            if surface.casefold() in _LEGAL_PHRASES:
                continue
            if _is_all_caps_section_header(surface):
                continue
            if not _LEGAL_FORM_RE.search(surface) and re.search(
                r"(?i)\b(leasingkohde|sopimusehdot|peruutusehdot)\b", surface
            ):
                continue
        if r.entity_type in {"LOCATION", "CITY"} and _looks_like_false_location(
            surface
        ):
            continue
        kept.append(r)
    return kept


def _block_ranges(blocks: list[str], sep: str = "\n\n") -> list[tuple[int, int]]:
    """Character ranges of each block inside ``sep.join(blocks)``."""
    ranges: list[tuple[int, int]] = []
    pos = 0
    for i, block in enumerate(blocks):
        if i:
            pos += len(sep)
        start = pos
        pos += len(block)
        ranges.append((start, pos))
    return ranges


def _project_results_to_block(
    results: list[RecognizerResult],
    block_start: int,
    block_end: int,
) -> list[RecognizerResult]:
    """Map document-level spans into one block's local coordinates.

    Overlapping entities are clipped to the block. Spans that only touch the
    block via a multi-block join are still applied on the overlapping slice
    (e.g. postcode+city line of a split Finnish address form).
    """
    local: list[RecognizerResult] = []
    for r in results:
        if r.end <= block_start or r.start >= block_end:
            continue
        ov_start = max(r.start, block_start)
        ov_end = min(r.end, block_end)
        loc_start = ov_start - block_start
        loc_end = ov_end - block_start
        if loc_end <= loc_start:
            continue
        local.append(
            RecognizerResult(
                entity_type=r.entity_type,
                start=loc_start,
                end=loc_end,
                score=r.score,
            )
        )
    return local


def apply_stable_placeholders(
    text: str,
    results: list[RecognizerResult],
    entity_map: EntityMap | None = None,
    *,
    style: str = "placeholder",
) -> tuple[str, EntityMap, list[EntityHit]]:
    """Replace spans with stable placeholders or delete them.

    ``style``:
      - ``placeholder`` (default): insert ``[TYPE_n]`` tags
      - ``remove``: delete the span (empty replacement)

    Map keys remain placeholder tags either way (for ``--map`` / counts).
    Indices follow first appearance (left-to-right); mutation is applied
    right-to-left so character offsets remain valid.
    """
    from anonymizer.anonymize.config import normalize_redact_style

    style = normalize_redact_style(style)
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
        replacement = "" if style == "remove" else placeholder
        chars[r.start : r.end] = list(replacement)
    out = "".join(chars)
    if style == "remove":
        # Collapse runs of spaces/tabs left by deletions (keep newlines).
        out = re.sub(r"[^\S\n]{2,}", " ", out)
    return out, entity_map, hits


class DocumentAnonymizer:
    """Anonymizer pipeline: patterns + heuristics + neural NER (+ optional LLM).

    Layers (no production search lists of companies/people):
      1. Structural patterns — IDs, plates, postcodes, URLs, legal-form morphology
      2. Heuristics — capitalisation, address shape, spaCy POS filters
      3. Neural NER — spaCy models for PERSON/ORG/LOCATION
      4. Optional LLM — surface extraction; may use synthetic few-shot *teaching*
         examples in the prompt (not grepped from user documents)
      5. User denylist/allowlist from config only

    Synthetic strings in tests or LLM prompts are for teaching/regression only.
    """

    def __init__(self, config: AnonymizerConfig | None = None) -> None:
        self.config = config or AnonymizerConfig()

    def analyze_text(
        self,
        text: str,
        language_decision: LanguageDecision | None = None,
        lang_flag: str | None = None,
        progress=None,  # Callable[[str], None] | None
        *,
        report_phases: bool = True,
    ) -> tuple[list[RecognizerResult], LanguageDecision]:
        def _p(msg: str) -> None:
            if progress and report_phases:
                progress(msg)

        flag = lang_flag if lang_flag is not None else self.config.lang
        # Rejoin PDF/OCR-split emails etc. so detectors see full surfaces
        text = repair_text_artifacts(text)

        if language_decision is None:
            _p("Detecting language…")
            decision = resolve_language(flag, text)
            _p(
                f"Language: {','.join(decision.detected) or '—'} "
                f"({decision.reason}) · NLP passes: {','.join(decision.nlp_passes)}"
            )
        else:
            decision = language_decision

        # extract mode: no entity detection
        if self.config.mode == "extract" or not self.config.effective_entities():
            if self.config.mode == "extract":
                _p("Mode extract — skipping redaction…")
            return [], decision

        entities = self.config.effective_entities()
        all_results: list[RecognizerResult] = []

        # Neural NER
        for lang in decision.nlp_passes:
            _p(f"Neural NER ({lang})…")
            all_results.extend(_spacy_ner_results(text, lang, entities))

        # Patterns + heuristics
        _p("Patterns & heuristics…")
        all_results.extend(
            _pattern_results(
                text,
                entities,
                score_threshold=self.config.score_threshold,
                include_ner=False,
            )
        )

        # Optional LLM
        if self.config.use_llm:
            _p(f"LLM entity layer ({self.config.llm_provider})…")
            try:
                from anonymizer.anonymize.llm import llm_entity_results

                all_results.extend(
                    llm_entity_results(
                        text,
                        entities,
                        provider=self.config.llm_provider,
                        model=self.config.llm_model,
                        ollama_url=self.config.ollama_url,
                    )
                )
            except Exception as exc:
                _p(f"LLM layer skipped: {exc}")
                logger.warning("LLM layer skipped: %s", exc)

        # User denylist (even in standard/strict when entities are set)
        if self.config.denylist:
            _p("Applying denylist…")
        all_results.extend(
            _denylist_hits(text, self.config.denylist, set(entities))
        )

        _p("Merging entities…")
        merged = _merge_results(all_results)
        merged = _filter_field_labels(text, merged)
        merged = _filter_false_org_location(text, merged)
        merged = _drop_noisy_surfaces(text, merged)

        # Propagate company stems (LähiTapiola Rahoitus Oy → LähiTapiola / LähiTapiolan)
        if "ORG" in entities:
            stems = collect_stems_from_results(text, merged)
            if stems:
                _p("Expanding company short forms…")
                merged = _merge_results(merged + expand_org_stems_in_text(text, stems))
                merged = _filter_false_org_location(text, merged)

        merged = _allowlist_filter(text, merged, self.config.allowlist)
        return merged, decision

    def anonymize_text(
        self,
        text: str,
        lang_flag: str | None = None,
        progress=None,
    ) -> AnonymizeResult:
        # Same repaired surface for detection + placeholders
        text = repair_text_artifacts(text)
        results, decision = self.analyze_text(
            text, lang_flag=lang_flag, progress=progress
        )
        if progress:
            progress("Applying redactions…")
        anonymized, entity_map, hits = apply_stable_placeholders(
            text, results, style=self.config.redact_style
        )
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
            mode=self.config.mode,
            redact_style=self.config.redact_style,
        )

    def anonymize_blocks(
        self,
        blocks_text_list: list[str],
        lang_flag: str | None = None,
        progress=None,
    ) -> tuple[list[str], AnonymizeResult]:
        """
        Anonymize blocks with a shared EntityMap.

        Runs detection **once** on the full joined document (fast path), then
        projects entity spans back onto each block for placeholder application.
        """
        def _p(msg: str) -> None:
            if progress:
                progress(msg)

        # Repair artifacts on each block so offsets match analysis
        blocks_text_list = [repair_text_artifacts(b) for b in blocks_text_list]
        ranges = _block_ranges(blocks_text_list, sep="\n\n")
        joined = "\n\n".join(blocks_text_list)
        flag = lang_flag if lang_flag is not None else self.config.lang
        n_blocks = sum(1 for b in blocks_text_list if b.strip())

        # extract: passthrough without NER/patterns
        if self.config.mode == "extract":
            _p(
                f"Extract only ({len(joined)} chars, {n_blocks} block(s)) — no redaction…"
            )
            decision = resolve_language(flag, joined) if joined.strip() else LanguageDecision(
                mode="forced" if flag and flag != "auto" else "auto",
                detected=[],
                nlp_passes=[],
                reason="extract mode",
            )
            summary = AnonymizeResult(
                anonymized_text=joined,
                entity_counts={},
                mapping={},
                language=decision,
                hits=[],
                mode="extract",
            )
            return list(blocks_text_list), summary

        _p(
            f"Analyzing full document ({len(joined)} chars, {n_blocks} block(s))…"
        )

        # Single-pass analysis (NER + patterns + optional LLM) — not per block
        results, decision = self.analyze_text(
            joined,
            lang_flag=flag,
            progress=progress,
            report_phases=True,
        )

        style = self.config.redact_style
        _p(
            "Applying redactions…"
            if style == "remove"
            else "Applying placeholders…"
        )
        entity_map = EntityMap()
        all_hits: list[EntityHit] = []
        out_blocks: list[str] = []
        type_counts: dict[str, int] = {}
        seen_keys: set[tuple[str, str]] = set()

        for block, (b_start, b_end) in zip(blocks_text_list, ranges, strict=True):
            if not block.strip():
                out_blocks.append(block)
                continue
            local = _project_results_to_block(results, b_start, b_end)
            anon, entity_map, hits = apply_stable_placeholders(
                block, local, entity_map=entity_map, style=style
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
            mode=self.config.mode,
            redact_style=style,
        )
        return out_blocks, summary
