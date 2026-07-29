"""Input path discovery and output path helpers."""

from __future__ import annotations

from pathlib import Path

from anonymizer.extract import SUPPORTED_EXTENSIONS


def collect_inputs(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {path.suffix}. "
                f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
            )
        return [path]
    if path.is_dir():
        files: list[Path] = []
        for p in sorted(path.rglob("*")):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(p)
        if not files:
            raise ValueError(f"No supported documents found in directory: {path}")
        return files
    raise FileNotFoundError(f"Path not found: {path}")


def default_output_path(input_path: Path, out_dir: Path | None = None) -> Path:
    name = f"{input_path.stem}.anonymized.md"
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / name
    return input_path.with_name(name)
