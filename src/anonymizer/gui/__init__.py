"""Desktop options UI (Windows primary; works on macOS for development)."""

from __future__ import annotations

__all__ = ["main"]


def main() -> None:
    from anonymizer.gui.app import main as _main

    _main()
