"""Install spaCy language models into the current Python environment.

Used by Homebrew post_install, install.sh / install.ps1, and manual recovery:

    python -m anonymizer.install_models --langs en,fi --size lg --fallback
    python -m anonymizer.install_models --check

**Precheck:** if all requested languages already have a loadable model, exit 0
immediately without any download (avoids false “install failed” on upgrades).

Models are installed from GitHub release wheels (not bare PyPI names like
``en_core_web_lg``, which pip cannot resolve).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Iterable, Sequence

# lang → size → package name
_MODEL_MATRIX: dict[str, dict[str, str]] = {
    "en": {
        "lg": "en_core_web_lg",
        "md": "en_core_web_md",
        "sm": "en_core_web_sm",
    },
    "fi": {
        "lg": "fi_core_news_lg",
        "md": "fi_core_news_md",
        "sm": "fi_core_news_sm",
    },
    "sv": {
        "lg": "sv_core_news_lg",
        "md": "sv_core_news_md",
        "sm": "sv_core_news_sm",
    },
}

_SIZE_FALLBACK = {
    "lg": ("lg", "md", "sm"),
    "md": ("md", "sm"),
    "sm": ("sm",),
}


def model_name(lang: str, size: str) -> str:
    lang = lang.lower().strip()
    size = size.lower().strip()
    if lang not in _MODEL_MATRIX:
        raise ValueError(f"Unknown language {lang!r}; known: {', '.join(_MODEL_MATRIX)}")
    if size not in _MODEL_MATRIX[lang]:
        raise ValueError(f"Unknown size {size!r}; use sm, md, or lg")
    return _MODEL_MATRIX[lang][size]


def candidates_for(lang: str, size: str, *, fallback: bool) -> list[str]:
    sizes = _SIZE_FALLBACK[size] if fallback else (size,)
    return [model_name(lang, s) for s in sizes]


def model_loadable(name: str) -> bool:
    try:
        import spacy

        spacy.load(name)
        return True
    except Exception:
        return False


def first_loadable(lang: str, size: str = "lg", *, fallback: bool = True) -> str | None:
    """Return first loadable package name for *lang*, or None."""
    try:
        chain = candidates_for(lang, size, fallback=fallback)
    except ValueError:
        return None
    for name in chain:
        if model_loadable(name):
            return name
    return None


def resolve_wheel_url(name: str) -> str:
    """Return GitHub release wheel URL for *name* matching installed spaCy."""
    from spacy.about import __download_url__ as base
    from spacy.cli.download import get_compatibility, get_version

    ver = get_version(name, get_compatibility())
    # Full URL — must not be truncated (missing .whl → HTTP 404)
    return f"{base}/{name}-{ver}/{name}-{ver}-py3-none-any.whl"


def ensure_pip() -> None:
    """Make sure ``python -m pip`` works for this interpreter."""
    r = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        return
    subprocess.run(
        [sys.executable, "-m", "ensurepip", "--upgrade"],
        check=False,
        capture_output=True,
    )
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        check=False,
        capture_output=True,
    )


def pip_install(url_or_spec: str) -> tuple[bool, str]:
    """Install with this interpreter's pip. Returns (ok, combined_output tail)."""
    ensure_pip()
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", url_or_spec],
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out[-2000:] if out else ""


def install_one(name: str, *, quiet: bool = False) -> bool:
    """Install a single model package; return True if loadable afterward."""
    if model_loadable(name):
        if not quiet:
            print(f"  {name}: already available")
        return True

    try:
        url = resolve_wheel_url(name)
    except Exception as exc:
        if not quiet:
            print(f"  {name}: could not resolve wheel URL ({exc})")
        return False

    if not quiet:
        print(f"  {name}: downloading…")
    ok, log = pip_install(url)
    if not ok:
        if not quiet:
            tail = log.strip().splitlines()[-3:] if log else []
            detail = "; ".join(tail) if tail else "pip failed"
            print(f"  {name}: install failed ({detail[:200]})")
        return False

    if model_loadable(name):
        if not quiet:
            print(f"  {name}: OK")
        return True

    if not quiet:
        print(f"  {name}: installed but spacy.load failed")
    return False


def precheck_langs(
    langs: Sequence[str],
    size: str = "lg",
    *,
    fallback: bool = True,
) -> dict[str, str | None]:
    """Map each lang → loadable package name (or None). No network."""
    out: dict[str, str | None] = {}
    for lang in langs:
        lang = lang.lower().strip()
        if not lang:
            continue
        out[lang] = first_loadable(lang, size, fallback=fallback)
    return out


def install_langs(
    langs: Sequence[str],
    size: str = "lg",
    *,
    fallback: bool = True,
    quiet: bool = False,
) -> dict[str, str | None]:
    """Install models for each language. Returns lang → package or None.

    Precheck: if every requested language already has a loadable model, skip
    all downloads and return those packages.
    """
    langs_clean = [x.lower().strip() for x in langs if x.strip()]
    pre = precheck_langs(langs_clean, size, fallback=fallback)

    if langs_clean and all(pre.get(lang) for lang in langs_clean):
        if not quiet:
            ready = " ".join(f"{k}={pre[k]}" for k in langs_clean)
            print(f"spaCy models already ready: {ready}")
            print(f"Summary: {ready} (ok)")
        return pre

    results: dict[str, str | None] = dict(pre)
    for lang in langs_clean:
        if results.get(lang):
            if not quiet:
                print(f"spaCy models ({lang}): already available ({results[lang]})")
            continue
        chosen: str | None = None
        try:
            chain = candidates_for(lang, size, fallback=fallback)
        except ValueError as exc:
            if not quiet:
                print(f"{lang}: {exc}")
            results[lang] = None
            continue
        if not quiet:
            print(f"spaCy models ({lang}):")
        for name in chain:
            if install_one(name, quiet=quiet):
                chosen = name
                break
            if fallback and name != chain[-1] and not quiet:
                print("  … trying smaller model")
        results[lang] = chosen
        if chosen is None and not quiet:
            print(f"  {lang}: FAILED (no model loadable)")

    # Final truth: re-scan loads (doctor-compatible)
    final = precheck_langs(langs_clean, size, fallback=fallback)
    if not quiet:
        parts = [f"{k}={final.get(k) or 'MISSING'}" for k in langs_clean]
        status = (
            "ok"
            if all(final.get(k) for k in langs_clean)
            else ("partial" if any(final.get(k) for k in langs_clean) else "failed")
        )
        print(f"Summary: {' '.join(parts)} ({status})")
    return final


def check_langs(langs: Iterable[str], size: str = "lg") -> dict[str, bool]:
    """Return whether each lang has any loadable model (lg→md→sm)."""
    out: dict[str, bool] = {}
    for lang in langs:
        lang = lang.lower().strip()
        if not lang:
            continue
        out[lang] = first_loadable(lang, size, fallback=True) is not None
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m anonymizer.install_models",
        description="Install spaCy NER models for anonymizer (EN/FI/SV).",
    )
    p.add_argument(
        "--langs",
        default="en,fi",
        help="Comma-separated language codes (default: en,fi). Optional: sv",
    )
    p.add_argument(
        "--size",
        choices=("sm", "md", "lg"),
        default="lg",
        help="Preferred model size (default: lg)",
    )
    p.add_argument(
        "--fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="On failure, try smaller sizes (default: yes)",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Only check whether models load; do not download",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Less output",
    )
    args = p.parse_args(argv)
    langs = [x.strip() for x in args.langs.split(",") if x.strip()]

    if args.check:
        status = check_langs(langs, args.size)
        for lang, ok in status.items():
            pkg = first_loadable(lang, args.size, fallback=True)
            if ok and pkg:
                print(f"{lang}: OK ({pkg})")
            else:
                print(f"{lang}: MISSING")
        return 0 if all(status.values()) else 1

    if not args.quiet:
        print(
            f"Ensuring spaCy models for {', '.join(langs)} "
            f"(preferred size={args.size})…"
        )
    results = install_langs(
        langs, args.size, fallback=args.fallback, quiet=args.quiet
    )
    ok_langs = [k for k, v in results.items() if v]
    bad_langs = [k for k, v in results.items() if not v]

    # Exit by final loadability (not download success)
    if not bad_langs:
        return 0
    if ok_langs:
        if not args.quiet:
            print(
                "Some languages still missing. See docs/models.md — "
                "no need to reinstall the app.",
                file=sys.stderr,
            )
        return 1
    if not args.quiet:
        print(
            "No requested models loadable. Retry install_models when online; "
            "do not reinstall the whole app.",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
