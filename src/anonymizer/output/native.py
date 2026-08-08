"""Dispatch native (original-format) redacted writers."""

from __future__ import annotations

import logging
from pathlib import Path

from anonymizer.anonymize.surfaces import RedactSurface, surfaces_from_mapping
from anonymizer.output.docx_redact import redact_docx
from anonymizer.output.native_stats import NativeRedactStats
from anonymizer.output.pdf_redact import redact_pdf

logger = logging.getLogger(__name__)

VALID_OUTPUT_FORMATS: tuple[str, ...] = ("md", "source", "both")
_FORMAT_ALIASES: dict[str, str] = {
    "md": "md",
    "markdown": "md",
    "source": "source",
    "native": "source",
    "original": "source",
    "both": "both",
    "all": "both",
    "dual": "both",
}


def normalize_output_format(value: str | None) -> str:
    """Map user format to md | source | both."""
    if value is None or not str(value).strip():
        return "md"
    key = str(value).strip().lower()
    if key not in _FORMAT_ALIASES:
        raise ValueError(
            f"Unknown output format {value!r}. Expected one of: "
            f"md, source, both (aliases: markdown, native, original, dual)."
        )
    return _FORMAT_ALIASES[key]


def wants_markdown(fmt: str) -> bool:
    return fmt in ("md", "both")


def wants_native(fmt: str) -> bool:
    return fmt in ("source", "both")


def native_suffix(input_path: Path) -> str | None:
    """Return .pdf / .docx if native redaction is supported for this file."""
    ext = input_path.suffix.lower()
    if ext == ".pdf":
        return ".pdf"
    if ext == ".docx":
        return ".docx"
    return None


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
) -> NativeRedactStats | None:
    """Write redacted original-format file. Returns None if type unsupported."""
    source = Path(source)
    dest = Path(dest)
    suf = native_suffix(source)
    if suf is None:
        return None
    surfaces: list[RedactSurface] = surfaces_from_mapping(mapping)
    if suf == ".pdf":
        return redact_pdf(source, surfaces, dest)
    if suf == ".docx":
        style = "remove" if redact_style == "remove" else "placeholder"
        return redact_docx(source, surfaces, dest, style=style)
    return None
