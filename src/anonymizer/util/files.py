"""Input path discovery and output path helpers."""

from __future__ import annotations

from pathlib import Path

from anonymizer.extract import SUPPORTED_EXTENSIONS


def format_supported_extensions() -> str:
    return ", ".join(sorted(SUPPORTED_EXTENSIONS))


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
                f"Unsupported file type: {path.suffix or '(none)'}. "
                f"Supported: {format_supported_extensions()}"
            )
        return [path]
    if path.is_dir():
        files: list[Path] = []
        for p in sorted(path.rglob("*")):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
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
