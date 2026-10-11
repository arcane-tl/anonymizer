"""Document-local company stem propagation (inflected short forms).

Also learns contract “hereinafter” aliases, e.g.::

    Oy Demofirma Ab (myöhemmin Demofirma)
    Demofirma Oy myöhemmin Demofirma
    Demofirma Oy (Demofirma)

Aliases are document-local only — never a hard-coded company catalog.
Generic roles (Asiakas, Toimittaja, Customer, …) are never learned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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

_LEGAL_TOKEN = re.compile(
    r"(?i)^(oyj|oy|abp|ab|ky|ltd\.?|limited|inc\.?|incorporated|"
    r"corp\.?|corporation|llc|llp|plc|gmbh|ag|sa|sas|bv|nv|"
    r"co\.|company|group|holdings?)$"
)

# Finnish case endings glued to the last stem token (longest first)
_FI_ENDINGS = (
    "lle|lta|ltä|ssa|ssä|sta|stä|lla|llä|ksi|na|nä|tta|ttä|"
    "in|aan|ään|een|iin|oon|öön|uun|yyn|"
    "n|a|ä|t"
)

# hereinafter / myöhemmin cues (FI + EN)
_ALIAS_CUE = (
    r"(?:myöhemmin|jäljempänä|jatkossa|tässä\s+sopimuksessa|"
    r"hereinafter|hereafter|later\s+referred\s+to\s+as|referred\s+to\s+as)"
)

# Alias capture: optional quotes, 1–4 Capitalized / ALLCAPS tokens
# (avoids swallowing trailing prose: "myöhemmin FirmaX tekee")
_ALIAS_BODY = (
    r"[\"'«»]?("
    r"[A-ZÅÄÖ][A-Za-zÅÄÖåäö0-9\-]*(?:[ \u00a0]+[A-ZÅÄÖ][A-Za-zÅÄÖåäö0-9\-]*){0,3}"
    r")[\"'«»]?"
)

# Cue is case-insensitive; alias body stays case-sensitive so lowercase
# prose after an inline cue is not swallowed (re.I would make [A-Z] match "tekee").
_CUE_PAREN_RE = re.compile(
    rf"\(\s*(?i:{_ALIAS_CUE})\s*[:\-]?\s*{_ALIAS_BODY}\s*\)",
    re.UNICODE,
)
_CUE_INLINE_RE = re.compile(
    rf"(?<![A-Za-zÅÄÖåäö0-9])(?i:{_ALIAS_CUE})\s+{_ALIAS_BODY}"
    rf"(?![A-Za-zÅÄÖåäö0-9])",
    re.UNICODE,
)
_BARE_PAREN_RE = re.compile(
    rf"\(\s*{_ALIAS_BODY}\s*\)",
    re.UNICODE,
)

# EN bare role words often used as hereinafter aliases — never expand
_ALIAS_ROLE_EXTRA = frozenset(
    {
        "company",
        "corporation",
        "entity",
        "organisation",
        "organization",
        "party",
        "parties",
    }
)

_MIN_ALIAS_LEN = 4
_BARE_PAREN_WINDOW = 80


@dataclass(frozen=True)
class OrgAliasBinding:
    """Alias learned from a contract intro, optionally tied to a full ORG surface."""

    alias: str
    primary: str | None = None  # full party surface when known


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
            rr = RecognizerResult(
                entity_type="ORG",
                start=start,
                end=end,
                score=score,
            )
            try:
                from anonymizer.anonymize.ner_meta import set_source

                set_source(rr, "org_stem")
            except Exception:
                pass
            results.append(rr)
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


def _normalize_alias_capture(raw: str) -> str:
    s = (raw or "").strip().strip("\"'«»").strip()
    s = re.sub(r"\s+", " ", s)
    # Drop leading EN/FI filler
    s = re.sub(r"(?i)^(the|as|nimellä|nimella)\s+", "", s).strip()
    return s


def usable_org_alias(alias: str) -> bool:
    """False for roles, weak stems, legal-form-only, or too-short aliases."""
    s = _normalize_alias_capture(alias)
    if not s or len(s) < _MIN_ALIAS_LEN:
        return False
    if any(ch.isdigit() for ch in s) and not re.search(r"[A-Za-zÅÄÖåäö]", s):
        return False
    key = s.casefold()
    if key in CONTRACT_ROLES or key in _ALIAS_ROLE_EXTRA:
        return False
    # Inflected role: Asiakkaan → check stem-ish strip of common FI ending
    role_stem = re.sub(
        r"(?i)(lle|lta|ltä|ssa|ssä|sta|stä|lla|llä|ksi|n)$", "", key
    )
    if role_stem in CONTRACT_ROLES or role_stem in _ALIAS_ROLE_EXTRA:
        return False
    if " " not in s and is_weak_org_stem(s):
        return False
    if _LEGAL_TOKEN.match(s):
        return False
    if _LEGAL.search(s) and len(s.split()) <= 2:
        # "(Ltd)" / "(Oy Ab)" style — not a party short name
        core = _LEGAL.sub("", s).strip()
        if not core or len(core) < _MIN_ALIAS_LEN:
            return False
    return True


def _core_tokens_from_org_surface(surface: str) -> set[str]:
    """Token set of the company core (legal form stripped), casefold."""
    s = surface.strip()
    s = re.sub(r"^[(\"«]+|[)\"»]+$", "", s).strip()
    # Strip trailing legal form repeatedly for "Oy Foo Ab"
    prev = None
    while prev != s:
        prev = s
        s = _LEGAL.sub("", s).strip(" ,.-")
    # Strip leading legal-form tokens (Oy Foo Ab)
    toks = [t for t in s.split() if t]
    while toks and _LEGAL_TOKEN.match(toks[0]):
        toks = toks[1:]
    return {t.casefold() for t in toks if t}


def _alias_overlaps_org(alias: str, org_surface: str) -> bool:
    """True when alias equals stripped stem or shares a content token."""
    alias_n = _normalize_alias_capture(alias)
    if not alias_n:
        return False
    cores = company_stems_from_org_surface(org_surface)
    alias_cf = alias_n.casefold()
    for core in cores:
        if alias_cf == core.casefold():
            return True
    org_toks = _core_tokens_from_org_surface(org_surface)
    alias_toks = {t.casefold() for t in alias_n.split() if t}
    if not org_toks or not alias_toks:
        return False
    return bool(alias_toks & org_toks)


def _nearest_org_surface(
    pos: int,
    org_spans: list[tuple[int, int, str]],
    *,
    window: int = _BARE_PAREN_WINDOW,
) -> str | None:
    """Preceding legal-form ORG surface within *window* chars before *pos*."""
    best: tuple[int, str] | None = None
    for start, end, surface in org_spans:
        if end > pos:
            continue
        if pos - end > window:
            continue
        if not company_stems_from_org_surface(surface):
            continue
        gap = pos - end
        if best is None or gap < best[0]:
            best = (gap, surface)
    return best[1] if best else None


def find_org_alias_bindings(
    text: str,
    results: list[RecognizerResult] | None = None,
) -> list[OrgAliasBinding]:
    """Learn document-local company aliases from contract intro phrasing."""
    if not text:
        return []
    org_spans: list[tuple[int, int, str]] = []
    for r in results or []:
        if r.entity_type != "ORG":
            continue
        surface = text[r.start : r.end]
        if company_stems_from_org_surface(surface):
            org_spans.append((r.start, r.end, surface))

    bindings: list[OrgAliasBinding] = []
    seen: set[str] = set()

    def _add(alias_raw: str, primary: str | None, *, require_overlap: bool) -> None:
        alias = _normalize_alias_capture(alias_raw)
        if not usable_org_alias(alias):
            return
        if require_overlap:
            if not primary or not _alias_overlaps_org(alias, primary):
                return
        key = alias.casefold()
        if key in seen:
            return
        seen.add(key)
        bindings.append(OrgAliasBinding(alias=alias, primary=primary))

    for m in _CUE_PAREN_RE.finditer(text):
        primary = _nearest_org_surface(m.start(), org_spans)
        _add(m.group(1), primary, require_overlap=False)

    for m in _CUE_INLINE_RE.finditer(text):
        # Skip if this span sits inside a cue-paren already handled
        if text[max(0, m.start() - 1) : m.start()] == "(":
            continue
        primary = _nearest_org_surface(m.start(), org_spans)
        _add(m.group(1), primary, require_overlap=False)

    for m in _BARE_PAREN_RE.finditer(text):
        # Skip cue-parens (already matched)
        inner = text[m.start() : m.end()]
        if re.search(_ALIAS_CUE, inner, flags=re.IGNORECASE):
            continue
        primary = _nearest_org_surface(m.start(), org_spans)
        _add(m.group(1), primary, require_overlap=True)

    return bindings


def find_org_aliases_in_text(
    text: str,
    results: list[RecognizerResult] | None = None,
) -> list[str]:
    """Alias strings only (for stem expansion)."""
    return [b.alias for b in find_org_alias_bindings(text, results)]


def merge_stems_with_aliases(
    stems: list[str],
    aliases: list[str] | list[OrgAliasBinding],
) -> list[str]:
    """Dedupe legal-form stems + hereinafter aliases (casefold)."""
    out: list[str] = []
    seen: set[str] = set()
    for st in stems:
        if not st:
            continue
        key = st.casefold()
        if key in seen or key in CONTRACT_ROLES or key in _ALIAS_ROLE_EXTRA:
            continue
        seen.add(key)
        out.append(st)
    for a in aliases:
        alias = a.alias if isinstance(a, OrgAliasBinding) else a
        if not usable_org_alias(alias):
            continue
        key = alias.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(alias)
    return out
