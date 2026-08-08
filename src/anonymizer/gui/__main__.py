"""Allow ``python -m anonymizer.gui`` on Windows launchers."""

from __future__ import annotations

from anonymizer.gui import main

if __name__ == "__main__":
    raise SystemExit(main())
