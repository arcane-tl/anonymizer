"""Repair PDF/OCR text artifacts that break PII detection.

Idempotent string fixes applied after extraction and again before analysis.
"""

from __future__ import annotations

import re

# Mid-TLD wrap only when the TLD so far is a *single* letter (clearly incomplete):
# user@domain.f\ni or user@domain.f i → user@domain.fi
# Do NOT match complete .com/.fi before " or" / " Phone".
_EMAIL_TLD_MID = re.compile(
    r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z])(?:\n|[ \t])([a-z]{1,3})\b"
)

# Soft split after @ : user@\nexample.com
_EMAIL_AT_SPLIT = re.compile(
    r"([A-Za-z0-9._%+\-]+@)\n([A-Za-z0-9.\-]+\.[A-Za-z]{2,24})\b"
)

# Domain label wrap: user@exam\nple.com
_EMAIL_DOMAIN_SPLIT = re.compile(
    r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]{1,60})\n([a-z0-9.\-]*\.[A-Za-z]{2,24})\b"
)

# Local-part wrap: first.last\n@example.com (rarer)
_EMAIL_LOCAL_SPLIT = re.compile(
    r"([A-Za-z0-9._%+\-]{2,64})\n(@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24})\b"
)

# Productive EN/FI prefixes that keep a real hyphen (pre-sales, e-mail, …).
_KEEP_HYPHEN_PREFIXES = frozenset(
    {
        "pre",
        "post",
        "non",
        "anti",
        "co",
        "e",
        "mid",
        "self",
        "cross",
        "multi",
        "sub",
        "inter",
        "intra",
        "mega",
        "micro",
        "semi",
        "quasi",
        "neo",
        "proto",
        "pseudo",
        "re",
        "ex",
        "pro",
        "meta",
        "over",
        "under",
        "out",
        "up",
        "off",
        "all",
        "no",
        "low",
        "high",
        "real",
        "near",
        "full",
        "well",
        "open",
        "front",
        "back",
        "left",
        "right",
        "top",
        "bottom",
        "one",
        "two",
        "three",
        "same",
        "long",
        "short",
        "on",
        "off",
        "in",
        "at",
        "to",
        "by",
        "of",
        "or",
        "and",
    }
)

# English (and a few FI) right-hand compound parts — keep the hyphen.
_KEEP_HYPHEN_RIGHTS = frozenset(
    {
        "sales",
        "stack",
        "time",
        "end",
        "up",
        "out",
        "in",
        "house",
        "site",
        "based",
        "free",
        "source",
        "level",
        "tech",
        "mail",
        "commerce",
        "business",
        "party",
        "op",
        "ops",
        "dev",
        "test",
        "prod",
        "stage",
        "ticket",
        "tickets",
        "tiketti",
        "tiketin",
        "tikettejä",
        "tiketteja",
        "known",
        "being",
        "made",
        "art",
        "house",
        "boarding",
        "demand",
        "premises",
        "person",
        "people",
        "code",
        "data",
        "service",
        "services",
        "line",
        "page",
        "size",
        "scale",
        "term",
        "terms",
        "form",
        "forms",
        "type",
        "types",
        "year",
        "years",
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
    }
)

# letter-letter soft hyphenation candidate (ASCII hyphen only; not en/em dash)
_SOFT_HYPHEN_PAIR = re.compile(
    r"(?<![A-Za-zÅÄÖåäö])"
    r"([A-Za-zÅÄÖåäö]{1,32})"
    r"-"
    r"([a-zåäö]{2,40})"
    r"(?![A-Za-zÅÄÖåäö])"
)


def should_keep_compound_hyphen(left: str, right: str) -> bool:
    """True when ``left-right`` is a real compound (pre-sales, Jira-tiketin, ETA-maat)."""
    if not left or not right:
        return True
    if any(ch.isdigit() for ch in left) or any(ch.isdigit() for ch in right):
        return True
    low_l = left.casefold()
    low_r = right.casefold()
    if low_l in _KEEP_HYPHEN_PREFIXES:
        return True
    if low_r in _KEEP_HYPHEN_RIGHTS:
        return True
    # Short ALLCAPS / acronym left: ETA-maat, EU-maat, IT-ala
    if left.isupper() and 1 <= len(left) <= 4:
        return True
    # Title-case / mixed proper noun: Jira-tiketin, SharePoint-x
    if left[0].isupper() and not left.isupper() and any(c.islower() for c in left):
        return True
    # Right starts with uppercase → keep
    if right[0].isupper():
        return True
    return False


def should_join_soft_hyphen(left: str, right: str) -> bool:
    """True when a hyphen is a syllable / line-wrap break to drop.

    Prefer missing a join over destroying real compounds or domain labels
    (``nordic-widgets.example.com``).
    """
    if should_keep_compound_hyphen(left, right):
        return False
    if not right or not right[0].islower():
        return False
    if not left.islower() or not right.islower():
        return False
    joined = left + right
    # Optional Voikko: joined Finnish word → drop hyphen
    try:
        from anonymizer.anonymize.voikko_fi import is_common_finnish_word

        flag = is_common_finnish_word(joined)
        if flag is True:
            return True
    except Exception:  # noqa: BLE001
        pass
    # Without Voikko (or unknown token): only join when Finnish letters appear,
    # so ASCII domain/email compounds like nordic-widgets stay intact.
    fi_chars = "åäöÅÄÖ"
    if any(c in fi_chars for c in left + right) and len(left) >= 2 and len(right) >= 4:
        return True
    return False


def repair_soft_hyphens(text: str) -> str:
    """Drop syllable / wrap hyphens; keep real compounds.

    Handles same-paragraph Word leftovers (``työ-kokemus``) and strips
    Unicode soft hyphens (U+00AD).
    """
    if not text:
        return text
    out = text.replace("\u00ad", "")
    if "-" not in out:
        return out

    def _repl(m: re.Match[str]) -> str:
        left, right = m.group(1), m.group(2)
        if should_join_soft_hyphen(left, right):
            return left + right
        return m.group(0)

    # Iterate: nested / multiple breaks in one paragraph
    prev = None
    for _ in range(6):
        if prev == out:
            break
        prev = out
        out = _SOFT_HYPHEN_PAIR.sub(_repl, out)
    return out


def repair_text_artifacts(text: str) -> str:
    """Rejoin identifiers broken by wraps; repair soft hyphenation."""
    if not text:
        return text
    out = repair_soft_hyphens(text)
    if "\n" not in out:
        return out
    prev = None
    # Iterate a few times for multiple breaks in one address
    for _ in range(4):
        if prev == out:
            break
        prev = out
        out = _EMAIL_TLD_MID.sub(r"\1\2", out)
        out = _EMAIL_AT_SPLIT.sub(r"\1\2", out)
        out = _EMAIL_DOMAIN_SPLIT.sub(r"\1\2", out)
        out = _EMAIL_LOCAL_SPLIT.sub(r"\1\2", out)
    return out


def is_real_web_url(surface: str) -> bool:
    """True for real web links — not bare name.xx FPs (firstname.xx)."""
    s = surface.strip().rstrip(".,;:!?)]}'\"")
    if not s:
        return False
    low = s.casefold()
    if low.startswith(("http://", "https://", "ftp://", "www.")):
        return True
    # Multi-label host: verkkopalvelu.lahitapiolarahoitus.fi
    if re.fullmatch(
        r"[a-z0-9][a-z0-9\-]*\.[a-z0-9][a-z0-9\-]*\.[a-z]{2,24}"
        r"(?:/[^\s]*)?",
        low,
    ):
        return True
    return False
