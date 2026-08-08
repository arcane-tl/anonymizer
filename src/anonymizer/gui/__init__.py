"""Desktop options UI (Windows primary; works on macOS for development)."""

from __future__ import annotations

__all__ = ["main"]


def main() -> int:
    from anonymizer.gui.app import main as _main

    return int(_main() or 0)
