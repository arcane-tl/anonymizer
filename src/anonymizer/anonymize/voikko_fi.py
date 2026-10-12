"""Optional libvoikko helper for Finnish common-word vs proper-name checks."""

from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path

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


def _dictionary_path() -> str | None:
    """Point the Python binding at a known library and return a dictionary root.

    The root is the directory that contains ``5/mor-standard``. ``None`` lets
    libvoikko use its default search (Homebrew on macOS).
    """
    try:
        import libvoikko  # type: ignore
    except ImportError:
        return None

    explicit = (os.environ.get("ANONYMIZER_VOIKKO_DIR") or "").strip()
    if sys.platform == "win32":
        candidates: list[Path] = []
        if explicit:
            candidates.append(Path(explicit))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "voikko")
        candidates.append(Path(sys.executable).resolve().parent / "voikko")
        for folder in candidates:
            if (folder / "libvoikko-1.dll").is_file():
                libvoikko.Voikko.setLibrarySearchPath(str(folder))
                if (folder / "5").is_dir():
                    return str(folder)
                return None
        return None

    if sys.platform == "darwin":
        for libdir in (explicit, "/opt/homebrew/lib", "/usr/local/lib"):
            if not libdir:
                continue
            if (Path(libdir) / "libvoikko.1.dylib").is_file():
                libvoikko.Voikko.setLibrarySearchPath(libdir)
                break
        for folder in (
            Path("/opt/homebrew/lib/voikko"),
            Path("/usr/local/lib/voikko"),
            Path.home() / ".voikko",
        ):
            if (folder / "5").is_dir():
                return str(folder)
    return None


@lru_cache(maxsize=1)
def voikko_available() -> tuple[bool, str]:
    """Return (ok, detail) for doctor / soft-skip."""
    try:
        import libvoikko  # type: ignore
    except ImportError:
        return False, "libvoikko Python package not installed"
    try:
        v = libvoikko.Voikko("fi", _dictionary_path())
    except Exception as exc:  # pragma: no cover - depends on system dicts
        return False, f"Voikko fi dictionary unavailable: {exc}"
    try:
        v.terminate()
    except Exception:
        pass
    return True, "libvoikko fi ok"


def voikko_install_check() -> tuple[bool, str]:
    """Installer and doctor gate.

    Passes only when Voikko loads and the common Finnish word ``kissa``
    analyzes as a non-name. The detail says which part failed.
    """
    ok, detail = voikko_available()
    if not ok:
        return False, detail
    result = is_common_finnish_word("kissa")
    if result is True:
        return True, "kissa analyzes as a Finnish word"
    return False, f"kissa did not analyze as a Finnish word ({result!r})"


@lru_cache(maxsize=1)
def _voikko():
    import libvoikko  # type: ignore

    return libvoikko.Voikko("fi", _dictionary_path())


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
