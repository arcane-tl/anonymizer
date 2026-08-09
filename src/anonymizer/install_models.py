"""Install spaCy language models into the current Python environment.

Used by Homebrew post_install, install.sh / install.ps1, and manual recovery:

    python -m anonymizer.install_models --langs en,fi --size lg --fallback
    python -m anonymizer.install_models --check

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
    # Bootstrap pip into this env
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
            print(f"  {name}: already installed")
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
            # One concise line; full log only on failure tail
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


def install_langs(
    langs: Sequence[str],
    size: str = "lg",
    *,
    fallback: bool = True,
    quiet: bool = False,
) -> dict[str, str | None]:
    """Install models for each language. Returns lang → installed package or None."""
    results: dict[str, str | None] = {}
    for lang in langs:
        lang = lang.lower().strip()
        if not lang:
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
                print(f"  … trying smaller model")
        results[lang] = chosen
        if chosen is None and not quiet:
            print(f"  {lang}: FAILED (no model loadable)")
    return results


def check_langs(langs: Iterable[str], size: str = "lg") -> dict[str, bool]:
    """Return whether the preferred model for each lang is loadable."""
    out: dict[str, bool] = {}
    for lang in langs:
        lang = lang.lower().strip()
        try:
            name = model_name(lang, size)
        except ValueError:
            out[lang] = False
            continue
        # Prefer any size if preferred missing? check preferred only
        out[lang] = model_loadable(name) or any(
            model_loadable(model_name(lang, s)) for s in ("lg", "md", "sm")
            if s in _MODEL_MATRIX.get(lang, {})
        )
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
            print(f"{lang}: {'OK' if ok else 'MISSING'}")
        return 0 if all(status.values()) else 1

    if not args.quiet:
        print(
            f"Installing spaCy models for {', '.join(langs)} "
            f"(preferred size={args.size})…"
        )
    results = install_langs(
        langs, args.size, fallback=args.fallback, quiet=args.quiet
    )
    ok_langs = [k for k, v in results.items() if v]
    bad_langs = [k for k, v in results.items() if not v]

    if not args.quiet:
        if ok_langs:
            print("Installed:", ", ".join(f"{k}={results[k]}" for k in ok_langs))
        if bad_langs:
            print(
                "Failed:",
                ", ".join(bad_langs),
                file=sys.stderr,
            )
            print(
                "Retry with network access, or see docs/models.md",
                file=sys.stderr,
            )

    if not bad_langs:
        return 0
    if ok_langs:
        return 1  # partial
    return 2  # total failure


if __name__ == "__main__":
    raise SystemExit(main())
