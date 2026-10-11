"""Optional libvoikko helper for Finnish common-word vs proper-name checks."""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# Voikko CLASS values that indicate a proper name (do not treat as common word)
_NAME_CLASSES = frozenset(
    {
        "etunimi",
        "sukunimi",
        "paikannimi",
        "nimi",
    }
)


@lru_cache(maxsize=1)
def voikko_available() -> tuple[bool, str]:
    """Return (ok, detail) for doctor / soft-skip."""
    try:
        import libvoikko  # type: ignore
    except ImportError:
        return False, "libvoikko Python package not installed"
    try:
        v = libvoikko.Voikko("fi")
    except Exception as exc:  # pragma: no cover - depends on system dicts
        return False, f"Voikko fi dictionary unavailable: {exc}"
    try:
        v.terminate()
    except Exception:
        pass
    return True, "libvoikko fi ok"


@lru_cache(maxsize=1)
def _voikko():
    import libvoikko  # type: ignore

    return libvoikko.Voikko("fi")


def is_common_finnish_word(surface: str) -> bool | None:
    """True if Voikko analyzes *surface* as a normal Finnish word (not a name).

    Returns ``None`` when Voikko is unavailable (caller should skip this gate).
    Returns ``False`` when unknown to Voikko or only name-class analyses exist.
    """
    word = (surface or "").strip()
    if not word or any(ch.isspace() for ch in word):
        return False
    ok, _ = voikko_available()
    if not ok:
        return None
    try:
        analyses = _voikko().analyze(word)
    except Exception as exc:  # pragma: no cover
        logger.debug("Voikko analyze failed for %r: %s", word, exc)
        return None
    if not analyses:
        return False
    classes = [str(a.get("CLASS", "")).casefold() for a in analyses]
    # Any name-class reading (etunimi / paikannimi / …) → possible proper name.
    # Avoids dropping brands like Nokia that also analyze as a common noun.
    if any(c in _NAME_CLASSES for c in classes):
        return False
    # Only non-name analyses → common word / compound
    if any(c and c not in _NAME_CLASSES for c in classes):
        return True
    return False


def all_tokens_common_finnish(tokens: list[str]) -> bool | None:
    """True if every token is a Voikko common word.

    Returns ``None`` when Voikko is unavailable or any token is inconclusive
    (``None``). Returns ``False`` if any token is not a common word.
    """
    cleaned = [t.strip(".,;:'\"()[]") for t in tokens if t and t.strip()]
    cleaned = [t for t in cleaned if t and not t.isdigit()]
    if not cleaned:
        return False
    ok, _ = voikko_available()
    if not ok:
        return None
    results: list[bool] = []
    for tok in cleaned:
        # Hyphenated compounds: require each side common when both alphabetic
        if "-" in tok and not tok.startswith("-"):
            parts = [p for p in tok.split("-") if p]
            if len(parts) >= 2 and all(p.isalpha() for p in parts):
                part_flags = [is_common_finnish_word(p) for p in parts]
                if any(f is None for f in part_flags):
                    return None
                if all(f is True for f in part_flags):
                    results.append(True)
                    continue
                results.append(False)
                continue
        flag = is_common_finnish_word(tok)
        if flag is None:
            return None
        results.append(bool(flag))
    if not results:
        return False
    return all(results)
