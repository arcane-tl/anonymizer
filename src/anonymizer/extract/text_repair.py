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


def repair_text_artifacts(text: str) -> str:
    """Rejoin identifiers broken by PDF line wraps (emails, etc.)."""
    if not text or "\n" not in text:
        return text
    prev = None
    out = text
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
    """True for real web links — not bare name.xx FPs (christofer.sj)."""
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
