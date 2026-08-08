"""Desktop options UI (Windows primary; works on macOS for development)."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

__all__ = ["main"]


def _bootstrap_log(msg: str) -> Path:
    """Write before any heavy imports so we always leave a breadcrumb."""
    base = os.environ.get("TEMP") or os.environ.get("TMP") or str(Path.home())
    path = Path(base) / "anonymizer-gui.log"
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except OSError:
        # Last resort: next to user home
        path = Path.home() / "anonymizer-gui.log"
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(msg.rstrip() + "\n")
        except OSError:
            pass
    return path


def main() -> int:
    log = _bootstrap_log(
        f"bootstrap: python={sys.executable!r} argv={sys.argv!r} cwd={os.getcwd()!r}"
    )
    try:
        from anonymizer.gui.app import main as _main

        code = int(_main() or 0)
        _bootstrap_log(f"bootstrap: exit code={code}")
        return code
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        log = _bootstrap_log(f"bootstrap CRASH:\n{tb}")
        # Visible even under pythonw
        try:
            if sys.platform == "win32":
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    0,
                    f"Anonymizer GUI failed to start:\n\n{exc}\n\nLog:\n{log}",
                    "Anonymizer",
                    0x10,
                )
            else:
                print(f"Anonymizer GUI failed: {exc}\nLog: {log}", file=sys.stderr)
        except Exception:
            print(f"Anonymizer GUI failed: {exc}\n{tb}", file=sys.stderr)
        return 1
