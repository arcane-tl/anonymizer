"""Dispatch native (original-format) redacted writers + output format parsing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Literal

from anonymizer.anonymize.surfaces import RedactSurface, surfaces_from_mapping
from anonymizer.output.docx_redact import redact_docx
from anonymizer.output.native_stats import NativeRedactStats
from anonymizer.output.pdf_redact import redact_pdf

logger = logging.getLogger(__name__)

OutputKind = Literal["md", "source", "pdf"]
OUTPUT_KINDS: tuple[OutputKind, ...] = ("md", "source", "pdf")

# Documented selectable kinds (multi via comma list).
VALID_OUTPUT_FORMATS: tuple[str, ...] = OUTPUT_KINDS

# Single token → one or more kinds.
_TOKEN_ALIASES: dict[str, frozenset[OutputKind]] = {
    "md": frozenset({"md"}),
    "markdown": frozenset({"md"}),
    "source": frozenset({"source"}),
    "native": frozenset({"source"}),
    "original": frozenset({"source"}),
    "pdf": frozenset({"pdf"}),
    "text-pdf": frozenset({"pdf"}),
    "text_pdf": frozenset({"pdf"}),
    # Compat / convenience combos
    "both": frozenset({"md", "source"}),
    "dual": frozenset({"md", "source"}),
    "all": frozenset({"md", "source", "pdf"}),
}


def parse_output_formats(value: str | Iterable[str] | None) -> frozenset[OutputKind]:
    """Parse ``--format`` / config into a non-empty frozenset of output kinds.

    Accepts a comma-separated string (``md,pdf``), a single alias (``both``),
    or an iterable of tokens. Default / empty → ``{md}``.
    """
    if value is None:
        return frozenset({"md"})
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return frozenset({"md"})
        # Accept comma / semicolon / whitespace / newlines (Mac GUI once
        # accidentally joined tokens with return instead of comma).
        normalized = raw.replace(";", ",").replace("\r", ",").replace("\n", ",")
        tokens = [t.strip() for t in normalized.split(",") if t.strip()]
        if len(tokens) == 1 and any(c.isspace() for c in tokens[0]):
            tokens = [t for t in tokens[0].split() if t.strip()]
    else:
        tokens = []
        for item in value:
            s = str(item).strip()
            if not s:
                continue
            if "," in s or ";" in s or "\n" in s or "\r" in s:
                tokens.extend(
                    t.strip()
                    for t in s.replace(";", ",")
                    .replace("\r", ",")
                    .replace("\n", ",")
                    .split(",")
                    if t.strip()
                )
            else:
                tokens.append(s)
        if not tokens:
            return frozenset({"md"})

    kinds: set[str] = set()
    unknown: list[str] = []
    for tok in tokens:
        key = tok.strip().lower()
        mapped = _TOKEN_ALIASES.get(key)
        if mapped is None:
            unknown.append(tok)
            continue
        kinds |= set(mapped)
    if unknown:
        raise ValueError(
            f"Unknown output format token(s): {', '.join(repr(u) for u in unknown)}. "
            f"Expected one or more of: md, source, pdf "
            f"(aliases: markdown, native, original, text-pdf; "
            f"compat: both=md+source, all=md+source+pdf)."
        )
    if not kinds:
        return frozenset({"md"})
    return frozenset(kinds)  # type: ignore[return-value]


def format_output_kinds(kinds: frozenset[OutputKind] | Iterable[str]) -> str:
    """Stable comma-joined canonical form (md, source, pdf order)."""
    s = frozenset(str(k) for k in kinds)
    return ",".join(k for k in OUTPUT_KINDS if k in s)


def normalize_output_format(value: str | None) -> str:
    """Normalize to a canonical comma-joined format string (default ``md``)."""
    return format_output_kinds(parse_output_formats(value))


def _as_kinds(fmt: str | frozenset[OutputKind] | Iterable[str]) -> frozenset[OutputKind]:
    if isinstance(fmt, frozenset):
        return fmt  # type: ignore[return-value]
    if isinstance(fmt, str):
        return parse_output_formats(fmt)
    return parse_output_formats(list(fmt))


def wants_markdown(fmt: str | frozenset[OutputKind] | Iterable[str]) -> bool:
    return "md" in _as_kinds(fmt)


def wants_native(fmt: str | frozenset[OutputKind] | Iterable[str]) -> bool:
    return "source" in _as_kinds(fmt)


def wants_text_pdf(fmt: str | frozenset[OutputKind] | Iterable[str]) -> bool:
    return "pdf" in _as_kinds(fmt)


def format_output_kinds(kinds: frozenset[OutputKind] | Iterable[str]) -> str:
    """Stable comma-joined canonical form (md, source, pdf order)."""
    s = frozenset(str(k) for k in kinds)
    return ",".join(k for k in OUTPUT_KINDS if k in s)


def native_suffix(input_path: Path) -> str | None:
    """Return .pdf / .docx if native redaction is supported for this file."""
    ext = input_path.suffix.lower()
    if ext == ".pdf":
        return ".pdf"
    if ext == ".docx":
        return ".docx"
    return None


def source_as_markdown(input_path: Path) -> bool:
    """True when ``--format source`` should write Markdown for this input.

    PDF/DOCX use layout-preserving native writers. Plain text (and other
    non-native types) fall back to ``{stem}.anonymized.md``.
    """
    return native_suffix(input_path) is None


def default_native_output_path(
    input_path: Path,
    out_dir: Path | None = None,
) -> Path:
    """``{stem}.anonymized.pdf`` / ``.docx`` next to source or under out_dir."""
    input_path = input_path.expanduser()
    suf = native_suffix(input_path)
    if suf is None:
        raise ValueError(f"No native output type for {input_path.suffix}")
    name = f"{input_path.stem}.anonymized{suf}"
    if out_dir is not None:
        out_dir = out_dir.expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / name
    return input_path.with_name(name)


def write_native_redacted(
    source: Path,
    dest: Path,
    mapping: dict[str, str],
    *,
    redact_style: str = "placeholder",
    redact_letterhead_images: bool = False,
) -> NativeRedactStats | None:
    """Write redacted original-format file. Returns None if type unsupported."""
    source = Path(source)
    dest = Path(dest)
    suf = native_suffix(source)
    if suf is None:
        return None
    surfaces: list[RedactSurface] = surfaces_from_mapping(mapping)
    if suf == ".pdf":
        return redact_pdf(
            source,
            surfaces,
            dest,
            redact_letterhead_images=redact_letterhead_images,
        )
    if suf == ".docx":
        style = "remove" if redact_style == "remove" else "placeholder"
        return redact_docx(source, surfaces, dest, style=style)
    return None
