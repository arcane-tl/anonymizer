"""Street / postcode / city address patterns (Finnish + common English).

Structured hits use specific entity types (hybrid model):

- ``STREET`` — street name + house number
- ``FI_POSTAL_CODE`` — five-digit postcode (when split from city)
- ``CITY`` — locality next to a postcode

Ambiguous geo from spaCy remains ``LOCATION`` (handled in the engine).
"""

from __future__ import annotations

import re
from typing import List, Optional

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# Finnish street-name endings (morphology, not a street catalog)
_FI_SUFFIX = (
    r"(?:katu|tie|kuja|polku|väylä|raitti|tori|aukio|puistikko|"
    r"ranta|mäki|rinne|bulevardi|esplanadi|puisto|kaari|penger|"
    r"silta|laituri|kallio|niemi|saari|kylä|kierto)"
)

# House / apartment: 17, 17a, 12B, 12-14, 12 A, 12 A 5
_HOUSE_NUM = (
    r"\s+\d{1,4}"
    r"(?:[A-Za-z]|-\d{1,4})?"
    r"(?:\s+[A-Za-z])?"
    r"(?:\s+\d{1,3})?"
)
_HOUSE_OPT = rf"(?:{_HOUSE_NUM})?"

_CITY = r"[A-ZÅÄÖ][A-Za-zÅÄÖåäö\-]{1,40}"
_FI_STREET_NAME = rf"[A-ZÅÄÖ][\wÅÄÖåäö\-]*{_FI_SUFFIX}"
_FI_STREET_CORE = rf"{_FI_STREET_NAME}(?:\s+[A-ZÅÄÖ][\wÅÄÖåäö\-]*)?"

_SPLIT_GAP = 160

# Space between postcode and city: horizontal (incl. NBSP) or a *single* newline.
# Never ``\n\n`` (would glue form fields: km-limit 23333 + Ylikilometriveloitus).
# PDFs often use \u00a0 between "05840" and "Hyvinkää".
_HSPACE = r"[ \t\u00a0\u202f\u2007\u2009]"
_PC_GAP = rf"(?:{_HSPACE}+|{_HSPACE}*\n{_HSPACE}*)"

# Commercial / fee-field words that are not place names
_NOT_CITY_SUFFIX = (
    r"(?:veloitus|maksu|palkkio|vuokra|vuokrat|ehdot|palvelut|palvelu|"
    r"yhteens[aä]|raja|kilometri|tunnit|er[aä]|osuu[s]?)$"
)
_NOT_CITY_RE = re.compile(_NOT_CITY_SUFFIX, re.IGNORECASE | re.UNICODE)


def _plausible_city_name(city: str) -> bool:
    c = city.strip()
    if len(c) < 2 or len(c) > 40:
        return False
    if _NOT_CITY_RE.search(c):
        return False
    # Long camel compounds without spaces are rarely cities
    if len(c) > 18 and "-" not in c and " " not in c:
        return False
    return True


# One-line FI: Street 17a, 02330 CITY → three components
_FI_FULL_DECOMP = re.compile(
    rf"(?<![A-Za-zÅÄÖåäö0-9])"
    rf"(?P<street>{_FI_STREET_CORE}{_HOUSE_NUM})"
    rf"\s*,\s*"
    rf"(?P<postal>\d{{5}})"
    rf"{_PC_GAP}"
    rf"(?P<city>{_CITY})"
    rf"(?![A-Za-zÅÄÖåäö0-9])",
    re.UNICODE,
)

_FI_FULL_DECOMP_LOOSE = re.compile(
    rf"(?<![A-Za-zÅÄÖåäö0-9])"
    rf"(?P<street>[A-ZÅÄÖ][A-Za-zÅÄÖåäö\-]{{2,40}}"
    rf"(?:[ \t]+[A-ZÅÄÖ][A-Za-zÅÄÖåäö\-]{{2,40}}){{0,2}}"
    rf"{_HOUSE_NUM})"
    rf"\s*,\s*"
    rf"(?P<postal>\d{{5}})"
    rf"{_PC_GAP}"
    rf"(?P<city>{_CITY})"
    rf"(?![A-Za-zÅÄÖåäö0-9])",
    re.UNICODE,
)

# Postcode + city (split or together)
_FI_POSTAL_CITY = re.compile(
    rf"(?:(?<=\s)|(?<=:)|(?<=^)|(?<=\n))"
    rf"(?P<postal>\d{{5}})"
    rf"{_PC_GAP}"
    rf"(?P<city>{_CITY})"
    rf"(?![A-Za-zÅÄÖåäö0-9])",
    re.UNICODE | re.MULTILINE,
)

# EN: "12 Baker Street, London"
# City multi-word uses horizontal space only (never newlines — avoids
# "San Francisco\nCustomer" when the next form label is Title Case).
_EN_FULL_DECOMP = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?P<street>\d{1,5}[A-Za-z]?[ \t]+"
    r"[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){0,3}[ \t]+"
    r"(?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Lane|Ln\.?|"
    r"Boulevard|Blvd\.?|Drive|Dr\.?|Way|Court|Ct\.?|Place|Pl\.?))"
    r"[ \t]*,[ \t]*"
    r"(?P<city>[A-Z][A-Za-z\-]+(?:[ \t]+[A-Z][A-Za-z\-]+){0,2})"
    r"(?![A-Za-z0-9])",
)

_FI_STREET = re.compile(
    rf"(?<!\w)"
    rf"("
    rf"{_FI_STREET_CORE}"
    rf"{_HOUSE_OPT}"
    rf")"
    rf"(?!\w)",
    re.UNICODE,
)

_EN_STREET = re.compile(
    r"(?<!\w)"
    r"("
    r"(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+"
    r"(?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Lane|Ln\.?|"
    r"Boulevard|Blvd\.?|Drive|Dr\.?|Way|Court|Ct\.?|Place|Pl\.?))"
    r")"
    r"(?:\s+\d{1,5}[A-Za-z]?)?"
    r"(?!\w)",
)

_FI_SPACED = re.compile(
    rf"(?<!\w)"
    rf"("
    rf"[A-ZÅÄÖ][\wÅÄÖåäö\-]*(?:\s+[A-ZÅÄÖ][\wÅÄÖåäö\-]*){{0,2}}\s+"
    rf"(?:katu|tie|kuja|polku|väylä|raitti|tori|aukio|kierto)"
    rf"{_HOUSE_OPT}"
    rf")"
    rf"(?!\w)",
    re.UNICODE | re.IGNORECASE,
)

_FI_STREET_WITH_HOUSE = re.compile(
    rf"(?<![A-Za-zÅÄÖåäö0-9])"
    rf"("
    rf"{_FI_STREET_CORE}"
    rf"{_HOUSE_NUM}"
    rf")"
    rf"(?![A-Za-zÅÄÖåäö0-9])",
    re.UNICODE,
)

# Typed hit: start, end, surface, score, entity_type
Hit = tuple[int, int, str, float, str]


def _merge_typed_hits(hits: list[Hit]) -> list[Hit]:
    """Merge overlaps: higher score wins; if equal prefer longer then higher-priority type."""
    priority = {"STREET": 3, "CITY": 3, "FI_POSTAL_CODE": 3, "LOCATION": 1}

    def sort_key(h: Hit):
        s, e, _v, score, et = h
        return (s, -(e - s), -score, -priority.get(et, 0))

    hits = sorted(hits, key=sort_key)
    merged: list[Hit] = []
    for hit in hits:
        start, end, value, score, et = hit
        conflict = False
        for i, prev in enumerate(merged):
            ps, pe, pv, pscore, pet = prev
            if start < pe and end > ps:
                conflict = True
                cur_len, prev_len = end - start, pe - ps
                cur_pri, prev_pri = priority.get(et, 0), priority.get(pet, 0)
                replace = False
                if score > pscore:
                    replace = True
                elif score == pscore:
                    if cur_pri > prev_pri:
                        replace = True
                    elif cur_pri == prev_pri and cur_len > prev_len:
                        replace = True
                if replace:
                    merged[i] = hit
                break
        if not conflict:
            merged.append(hit)
    return sorted(merged, key=lambda h: h[0])


def _between_is_form_noise(between: str) -> bool:
    if len(between) > _SPLIT_GAP:
        return False
    if re.search(r"(?<!\d)\d{5}(?!\d)", between):
        return False
    if "@" in between or "://" in between:
        return False
    return True


def _add_postal_city_groups(m: re.Match[str], score: float, hits: list[Hit]) -> None:
    postal = m.group("postal")
    city = m.group("city")
    # Guard against newline-glued form labels in city group
    if "\n" in city or "\r" in city:
        city = re.split(r"[\r\n]+", city, maxsplit=1)[0].strip()
        if not city:
            hits.append((m.start("postal"), m.end("postal"), postal, score, "FI_POSTAL_CODE"))
            return
        city_end = m.start("city") + len(city)
    else:
        city_end = m.end("city")
    if not _plausible_city_name(city):
        # Keep bare postal only when city is garbage (still may be real postcode)
        hits.append((m.start("postal"), m.end("postal"), postal, score * 0.9, "FI_POSTAL_CODE"))
        return
    hits.append((m.start("postal"), m.end("postal"), postal, score, "FI_POSTAL_CODE"))
    hits.append((m.start("city"), city_end, city, score, "CITY"))


def find_address_hits(text: str) -> list[Hit]:
    """Return typed address component hits."""
    hits: list[Hit] = []

    # One-line full FI addresses → STREET + POSTAL + CITY
    for pattern, score in (
        (_FI_FULL_DECOMP, 0.96),
        (_FI_FULL_DECOMP_LOOSE, 0.94),
    ):
        for m in pattern.finditer(text):
            street = m.group("street").strip()
            hits.append((m.start("street"), m.end("street"), street, score, "STREET"))
            _add_postal_city_groups(m, score, hits)

    # EN one-line → STREET + CITY
    for m in _EN_FULL_DECOMP.finditer(text):
        street = m.group("street").strip()
        city = m.group("city").strip()
        if "\n" in city or "\r" in city or "\n" in street:
            city = re.split(r"[\r\n]+", city, maxsplit=1)[0].strip()
        if not city:
            continue
        hits.append((m.start("street"), m.end("street"), street, 0.93, "STREET"))
        city_end = m.start("city") + len(city)
        hits.append((m.start("city"), city_end, city, 0.93, "CITY"))

    # Split-form: street line + later postcode/city
    streets = list(_FI_STREET_WITH_HOUSE.finditer(text))
    postal_cities = list(_FI_POSTAL_CITY.finditer(text))
    used_pc: set[int] = set()
    for sm in streets:
        s_start, s_end = sm.start(1), sm.end(1)
        best = None
        for pm in postal_cities:
            p_start = pm.start("postal")
            if p_start <= s_end or p_start in used_pc:
                continue
            between = text[s_end:p_start]
            if not _between_is_form_noise(between):
                continue
            if best is None or p_start < best[0]:
                best = pm
        if best is None:
            continue
        used_pc.add(best.start("postal"))
        street_val = text[s_start:s_end]
        hits.append((s_start, s_end, street_val, 0.96, "STREET"))
        _add_postal_city_groups(best, 0.96, hits)

    # Standalone postcode + city (not only when linked to street)
    for m in _FI_POSTAL_CITY.finditer(text):
        _add_postal_city_groups(m, 0.91, hits)

    # Street-only
    for pattern in (_FI_STREET, _FI_SPACED, _EN_STREET):
        for m in pattern.finditer(text):
            value = m.group(0).strip()
            if len(value) < 5:
                continue
            if value.casefold() in {"katu", "tie", "street", "road", "kierto"}:
                continue
            hits.append((m.start(), m.end(), value, 0.85, "STREET"))

    return _merge_typed_hits(hits)


def find_streets(text: str) -> list[tuple[int, int, str]]:
    """Legacy helper: street surfaces only."""
    return [(s, e, v) for s, e, v, _sc, et in find_address_hits(text) if et == "STREET"]


def find_address_spans(text: str) -> list[tuple[int, int, str, float]]:
    """Legacy helper without entity type (tests)."""
    return [(s, e, v, sc) for s, e, v, sc, _et in find_address_hits(text)]


class StreetRecognizer(EntityRecognizer):
    """Emit STREET, FI_POSTAL_CODE, and CITY for structured address parts."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["STREET", "CITY", "FI_POSTAL_CODE", "LOCATION"],
            supported_language="en",
            name="StreetRecognizer",
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
        wanted = set(entities) if entities else None
        results: list[RecognizerResult] = []
        for start, end, _value, score, etype in find_address_hits(text):
            if wanted and etype not in wanted:
                # FI_POSTAL_CODE might be requested as POSTAL alias — not used
                continue
            results.append(
                RecognizerResult(
                    entity_type=etype,
                    start=start,
                    end=end,
                    score=score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=score,
                        pattern_name=etype.lower(),
                        pattern="structured_address",
                        validation_result=True,
                    ),
                )
            )
        return results
