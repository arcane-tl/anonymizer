"""Input path discovery and output path helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anonymizer.extract import SUPPORTED_EXTENSIONS

# Stable README anchor (GitHub slug for "## Supported file types")
SUPPORTED_TYPES_README_URL = (
    "https://github.com/arcane-tl/anonymizer#supported-file-types"
)

# Human-friendly list for dialogs (extensions stay in format_supported_extensions).
SUPPORTED_TYPES_HUMAN = "PDF, Word (.docx), or plain text / Markdown"


def format_supported_extensions() -> str:
    return ", ".join(sorted(SUPPORTED_EXTENSIONS))


@dataclass(frozen=True)
class UnsupportedTypeNotice:
    """Structured notice for unsupported inputs (CLI + GUI dialogs)."""

    title: str
    file_line: str
    hint: str
    action: str
    supported_line: str
    url: str = SUPPORTED_TYPES_README_URL

    def body(self, *, include_url: bool = True) -> str:
        """Multi-line body suitable for dialogs and terminal output."""
        parts = [self.file_line]
        if self.hint:
            parts.extend(["", self.hint])
        parts.extend(["", self.action, "", self.supported_line])
        if include_url:
            # URL alone on the last line → terminals often auto-link it.
            parts.extend(["", self.url])
        return "\n".join(parts)

    def as_text(self) -> str:
        return f"{self.title}\n\n{self.body(include_url=True)}"


def unsupported_type_notice(
    suffix: str | None, *, path_hint: str | None = None
) -> UnsupportedTypeNotice:
    """Build a readable convert-first notice for an unsupported extension."""
    ext = (suffix or "").strip().lower()
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    label = ext if ext else "(no extension)"

    if path_hint:
        file_line = f"{path_hint}  ·  {label}"
    else:
        file_line = label

    if ext == ".gdoc":
        hint = (
            "That looks like a Google Docs shortcut (not the document itself).\n"
            "In Google Docs: File → Download → Microsoft Word (.docx) or PDF Document."
        )
    elif ext == ".pages":
        hint = (
            "That looks like a Mac Pages document.\n"
            "In Pages: File → Export To → Word or PDF."
        )
    elif ext in {".doc", ".odt", ".rtf"}:
        hint = "Save or export as Word (.docx) or PDF first."
    else:
        hint = ""

    return UnsupportedTypeNotice(
        title="Unsupported file type",
        file_line=file_line,
        hint=hint,
        action=f"Convert it to {SUPPORTED_TYPES_HUMAN}, then try again.",
        supported_line=f"Supported extensions: {format_supported_extensions()}",
        url=SUPPORTED_TYPES_README_URL,
    )


def unsupported_type_message(suffix: str | None, *, path_hint: str | None = None) -> str:
    """User-facing notice when a file type cannot be anonymized yet.

    Multi-line text with the README URL on its own line (clickable in many terminals).
    """
    return unsupported_type_notice(suffix, path_hint=path_hint).as_text()


def expand_user_path(path: Path) -> Path:
    """Expand leading ``~`` / ``~user`` so shell-style home paths work.

    Typer/Click pass Path values without expanding ``~``, so
    ``~/Documents/x.pdf`` would otherwise be treated as a relative path
    under a literal ``~`` directory.
    """
    return path.expanduser()


def collect_inputs(path: Path) -> list[Path]:
    path = expand_user_path(path)
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                unsupported_type_message(path.suffix, path_hint=path.name)
            )
        return [path]
    if path.is_dir():
        files: list[Path] = []
        root_resolved = path.resolve()
        for p in sorted(path.rglob("*")):
            # Skip symlink files/dirs (avoid following planted links outside root)
            try:
                if p.is_symlink():
                    continue
                if not p.is_file():
                    continue
                # Ensure resolved path stays under the requested directory
                resolved = p.resolve()
                if not resolved.is_relative_to(root_resolved):
                    continue
            except (OSError, ValueError):
                continue
            if p.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(p)
        if not files:
            raise ValueError(
                f"No supported documents found in {path}. "
                f"Looking for: {format_supported_extensions()}"
            )
        return files
    # Friendlier not-found
    hint = ""
    parent = path.parent
    if parent.is_dir():
        close = [
            p.name
            for p in parent.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ][:5]
        if close:
            hint = f" Nearby files: {', '.join(close)}."
    raise FileNotFoundError(
        f"Path not found: {path}.{hint} "
        f"Check the path (tab-complete helps) or drag the file into the terminal."
    )


def default_output_path(
    input_path: Path,
    out_dir: Path | None = None,
    *,
    mode: str = "strict",
) -> Path:
    """Choose a default Markdown path; never overwrite the source file."""
    input_path = expand_user_path(input_path)
    if mode == "extract":
        # Prefer stem.md next to the source; avoid clobbering a .md input
        candidate = input_path.with_name(f"{input_path.stem}.md")
        if candidate.resolve() == input_path.resolve():
            name = f"{input_path.stem}.extracted.md"
        else:
            name = f"{input_path.stem}.md"
    else:
        name = f"{input_path.stem}.anonymized.md"

    if out_dir is not None:
        out_dir = expand_user_path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / name
    return input_path.with_name(name)


def default_native_output_path(
    input_path: Path,
    out_dir: Path | None = None,
) -> Path:
    """``{stem}.anonymized.pdf`` / ``.docx`` next to source (or under out_dir)."""
    from anonymizer.output.native import default_native_output_path as _native_path

    return _native_path(expand_user_path(input_path), out_dir)


def default_text_pdf_output_path(
    input_path: Path,
    out_dir: Path | None = None,
) -> Path:
    """``{stem}.anonymized.text.pdf`` — reflow PDF from Markdown (not native redact)."""
    input_path = expand_user_path(input_path)
    name = f"{input_path.stem}.anonymized.text.pdf"
    if out_dir is not None:
        out_dir = expand_user_path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / name
    return input_path.with_name(name)
