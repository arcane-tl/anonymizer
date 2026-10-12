"""Runtime progress reporting with elapsed timer (stderr via Rich).

When ``ANONYMIZER_PROGRESS_FILE`` is set, the same steps are also written as
one JSON object (replaced atomically) so a GUI can show a quiet progress strip.
``--quiet`` still suppresses stderr. It does not suppress the status file.

``ANONYMIZER_PROGRESS_INDEX`` / ``ANONYMIZER_PROGRESS_TOTAL`` override the
in-process counts. The Mac shell and Windows GUI run one CLI process per file,
so the parent supplies the batch position.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path

from rich.console import Console

# Short labels for the progress strip. Raw engine text stays on stderr.
_PHASE_READING = "Reading the document"
_PHASE_FINDING = "Finding sensitive data"
_PHASE_REVIEW = "Waiting for review"
_PHASE_WRITING = "Writing files"
_PHASE_STARTING = "Starting"

# How far through the current file each phase sits (0–1). Not a real NER percent.
_PHASE_WITHIN = {
    _PHASE_STARTING: 0.05,
    _PHASE_READING: 0.25,
    _PHASE_FINDING: 0.6,
    _PHASE_REVIEW: 0.8,
    _PHASE_WRITING: 0.92,
}


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
        status_path: Path | str | None = None,
    ) -> None:
        self.console = console or Console(stderr=True)
        self.quiet = quiet
        self._doc_t0: float | None = None
        self._batch_t0: float | None = None
        self._doc_index = 0
        self._doc_total = 0
        self._phase = _PHASE_STARTING
        self._file_name = ""
        if status_path is not None:
            self._status_path: Path | None = Path(status_path)
        else:
            raw = (os.environ.get("ANONYMIZER_PROGRESS_FILE") or "").strip()
            self._status_path = Path(raw) if raw else None

    def start_batch(self, total: int) -> None:
        self._batch_t0 = time.perf_counter()
        self._doc_total = total

    def start_document(self, path: Path | str, index: int = 1, total: int = 1) -> None:
        self._doc_t0 = time.perf_counter()
        index, total = self._batch_position(index, total)
        self._doc_index = index
        self._doc_total = total
        name = Path(path).name
        self._file_name = name
        self._phase = _PHASE_STARTING
        if total > 1:
            self.step(f"Document {index}/{total}: {name}")
        else:
            self.step(f"Document: {name}")
        self._publish(state="running")

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
        self._phase = phase_for_message(message)
        self._print(f"  → {message}")
        self._publish(state="running")

    def done_document(self, summary: str) -> None:
        """Final success line with elapsed time."""
        if not self.quiet:
            t = self.elapsed_str().strip()
            self.console.print(
                f"[dim]\\[{self.elapsed_str()}][/dim] [green]✓[/green] Done in {t} · {summary}"
            )
        # Stay ``running``. The parent process writes ``done`` when the batch
        # ends so a one-CLI-per-file loop does not close the strip early.
        self._publish(state="running", within=1.0)

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

    def _batch_position(self, index: int, total: int) -> tuple[int, int]:
        raw_total = (os.environ.get("ANONYMIZER_PROGRESS_TOTAL") or "").strip()
        raw_index = (os.environ.get("ANONYMIZER_PROGRESS_INDEX") or "").strip()
        if raw_total.isdigit() and int(raw_total) > 0:
            total = int(raw_total)
        if raw_index.isdigit() and int(raw_index) > 0:
            index = int(raw_index)
        return index, total

    def _publish(self, *, state: str, within: float | None = None) -> None:
        if self._status_path is None:
            return
        if within is None:
            within = _PHASE_WITHIN.get(self._phase, 0.4)
        total = max(self._doc_total, 1)
        index = max(self._doc_index, 1) if self._doc_index else 0
        if index <= 0:
            fraction = 0.0
        else:
            fraction = ((index - 1) + within) / total
        try:
            write_progress_status(
                self._status_path,
                state=state,
                phase=self._phase,
                index=index,
                total=max(self._doc_total, 0),
                file=self._file_name,
                fraction=fraction,
            )
        except OSError:
            return


def noop_progress(_message: str) -> None:
    """No-op progress callback for tests / quiet library use."""
    return None


def phase_for_message(message: str) -> str:
    """Map an engine/CLI progress line to a short strip label."""
    m = message.casefold()
    if "review" in m:
        return _PHASE_REVIEW
    if any(k in m for k in ("writing", "rendering", "delete style")):
        return _PHASE_WRITING
    if any(k in m for k in ("extract", "reading", "ocr", "text layer")):
        return _PHASE_READING
    if any(
        k in m
        for k in (
            "neural",
            "pattern",
            "language",
            "llm",
            "denylist",
            "merging",
            "expanding",
            "redaction",
            "detecting",
            "heuristic",
        )
    ):
        return _PHASE_FINDING
    cleaned = message.replace("…", "").strip()
    return cleaned or _PHASE_STARTING


def write_progress_status(
    path: Path | str,
    *,
    state: str,
    phase: str = "",
    index: int = 0,
    total: int = 0,
    file: str = "",
    fraction: float = 0.0,
) -> None:
    """Replace ``path`` with one JSON object. Readers never see a partial write."""
    dest = Path(path)
    payload = {
        "state": state,
        "phase": phase,
        "index": int(index),
        "total": int(total),
        "file": file,
        "fraction": max(0.0, min(1.0, float(fraction))),
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, dest)
