"""Local document anonymizer: PDF/DOCX/text → anonymized Markdown."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def _read_version() -> str:
    try:
        return version("anonymizer")
    except PackageNotFoundError:
        pass
    # Editable / bare tree: fall back to pyproject.toml next to src/
    try:
        import tomllib
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        return str(data["project"]["version"])
    except Exception:
        return "0.0.0+dev"


__version__ = _read_version()
