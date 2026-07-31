"""Runtime progress reporting with elapsed timer (stderr via Rich)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from rich.console import Console


def format_elapsed(seconds: float) -> str:
    """Human-readable elapsed time for progress lines."""
    if seconds < 60:
        return f"{seconds:5.1f}s"
    minutes = int(seconds // 60)
    rem = seconds - minutes * 60
    return f"{minutes}m{rem:04.1f}s"


class RunProgress:
    """Print clear pipeline steps with a per-document elapsed timer."""

    def __init__(
        self,
        console: Console | None = None,
        *,
        quiet: bool = False,
    ) -> None:
        self.console = console or Console(stderr=True)
        self.quiet = quiet
        self._doc_t0: float | None = None
        self._batch_t0: float | None = None
        self._doc_index = 0
        self._doc_total = 0

    def start_batch(self, total: int) -> None:
        self._batch_t0 = time.perf_counter()
        self._doc_total = total

    def start_document(self, path: Path | str, index: int = 1, total: int = 1) -> None:
        self._doc_t0 = time.perf_counter()
        self._doc_index = index
        self._doc_total = total
        name = Path(path).name
        if total > 1:
            self.step(f"Document {index}/{total}: {name}")
        else:
            self.step(f"Document: {name}")

    def elapsed(self) -> float:
        if self._doc_t0 is None:
            return 0.0
        return time.perf_counter() - self._doc_t0

    def elapsed_str(self) -> str:
        return format_elapsed(self.elapsed())

    def batch_elapsed_str(self) -> str:
        if self._batch_t0 is None:
            return format_elapsed(0.0)
        return format_elapsed(time.perf_counter() - self._batch_t0)

    def _print(self, line: str) -> None:
        if self.quiet:
            return
        # Escape [time] so Rich does not treat it as markup
        t = self.elapsed_str()
        self.console.print(f"[dim]\\[{t}][/dim] {line}")

    def step(self, message: str) -> None:
        """Top-level timed step line."""
        self._print(message)

    def substep(self, message: str) -> None:
        """Indented timed sub-step (what is happening now)."""
        self._print(f"  → {message}")

    def done_document(self, summary: str) -> None:
        """Final success line with elapsed time."""
        if self.quiet:
            return
        t = self.elapsed_str().strip()
        self.console.print(
            f"[dim]\\[{self.elapsed_str()}][/dim] [green]✓[/green] Done in {t} · {summary}"
        )

    def done_batch(self, ok_count: int, total: int) -> None:
        if self.quiet or total <= 1:
            return
        bt = self.batch_elapsed_str().strip()
        self.console.print(
            f"[bold]Batch complete:[/bold] {ok_count}/{total} files in {bt}"
        )

    def as_callback(self) -> Callable[[str], None]:
        """Callback suitable for extract/engine ``progress=`` arguments."""
        return self.substep


def noop_progress(_message: str) -> None:
    """No-op progress callback for tests / quiet library use."""
    return None
