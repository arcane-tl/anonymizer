"""Document-local company stem propagation (inflected short forms)."""

from __future__ import annotations

import re

from presidio_analyzer import RecognizerResult

from anonymizer.anonymize.domain_lexicon import (
    CONTRACT_ROLES,
    is_weak_org_stem,
)

_LEGAL = re.compile(
    r"(?i)\b(oyj|oy\s+ab|oy|abp|ab|ky|ltd\.?|limited|inc\.?|incorporated|"
    r"corp\.?|corporation|llc|llp|plc|gmbh|ag|sa|sas|bv|nv|"
    r"co\.|company|group|holdings?)\s*$"
)

# Finnish case endings glued to the last stem token (longest first)
_FI_ENDINGS = (
    "lle|lta|ltä|ssa|ssä|sta|stä|lla|llä|ksi|na|nä|tta|ttä|"
    "in|aan|ään|een|iin|oon|öön|uun|yyn|"
    "n|a|ä|t"
)


def company_stems_from_org_surface(surface: str) -> list[str]:
    """From 'LähiTapiola Rahoitus Oy' → ['LähiTapiola Rahoitus', 'LähiTapiola']."""
    s = surface.strip()
    s = re.sub(r"^[(\"«]+|[)\"»]+$", "", s).strip()
    if not _LEGAL.search(s):
        return []
    core = _LEGAL.sub("", s).strip(" ,.-")
    if not core or len(core) < 4:
        return []
    tokens = core.split()
    stems: list[str] = []
    # Full name without legal form
    stems.append(core)
    # Leading token only (brand) if multi-word and not a weak generic
    if len(tokens) >= 2:
        first = tokens[0]
        if len(first) >= 4 and not is_weak_org_stem(first):
            stems.append(first)
    out: list[str] = []
    seen: set[str] = set()
    for st in stems:
        key = st.casefold()
        if key in seen:
            continue
        # Reject pure role / legalish single tokens
        if " " not in st and is_weak_org_stem(st):
            continue
        if key in CONTRACT_ROLES:
            continue
        seen.add(key)
        out.append(st)
    return out


def expand_org_stems_in_text(
    text: str,
    stems: list[str],
    *,
    score: float = 0.87,
) -> list[RecognizerResult]:
    """Find stem (+ optional FI case ending) occurrences as ORG."""
    if not stems or not text:
        return []
    results: list[RecognizerResult] = []
    seen: set[tuple[int, int]] = set()
    # Longest stems first
    for stem in sorted(stems, key=len, reverse=True):
        if len(stem) < 4:
            continue
        # Escape stem; allow flexible hyphen/space
        esc = re.escape(stem)
        esc = esc.replace(r"\-", r"[\- ]?")
        pat = re.compile(
            rf"(?<![A-Za-zÅÄÖåäö0-9])({esc})(?:{_FI_ENDINGS})?(?![A-Za-zÅÄÖåäö0-9])",
            re.IGNORECASE | re.UNICODE,
        )
        for m in pat.finditer(text):
            span = (m.start(1), m.end())  # include case ending in span
            # Actually group 1 is stem only; full match includes ending
            start, end = m.start(), m.end()
            span = (start, end)
            if span in seen:
                continue
            # Skip if this span is only a role / weak generic
            surf = text[start:end]
            if is_weak_org_stem(surf) or surf.casefold().rstrip("n") in CONTRACT_ROLES:
                continue
            seen.add(span)
            results.append(
                RecognizerResult(
                    entity_type="ORG",
                    start=start,
                    end=end,
                    score=score,
                )
            )
    return results


def collect_stems_from_results(
    text: str, results: list[RecognizerResult]
) -> list[str]:
    stems: list[str] = []
    seen: set[str] = set()
    for r in results:
        if r.entity_type != "ORG":
            continue
        surface = text[r.start : r.end]
        for st in company_stems_from_org_surface(surface):
            key = st.casefold()
            if key not in seen:
                seen.add(key)
                stems.append(st)
    return stems
