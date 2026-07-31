"""Tests for runtime progress helper."""

from pathlib import Path

from rich.console import Console

from anonymizer.util.progress import RunProgress, format_elapsed, noop_progress


def test_format_elapsed_seconds():
    assert "1.5s" in format_elapsed(1.5)
    assert "0.0s" in format_elapsed(0.0)


def test_format_elapsed_minutes():
    s = format_elapsed(65.2)
    assert "1m" in s


def test_noop_progress():
    noop_progress("anything")


def test_run_progress_records_steps(tmp_path: Path):
    console = Console(stderr=True, force_terminal=False, record=True)
    p = RunProgress(console, quiet=False)
    p.start_batch(1)
    p.start_document(tmp_path / "doc.txt", 1, 1)
    p.substep("Extracting…")
    p.substep("Neural NER (en)…")
    p.done_document("entities: none")
    text = console.export_text()
    assert "Document:" in text
    assert "Extracting" in text
    assert "Neural NER" in text
    assert "Done" in text


def test_quiet_suppresses_steps(tmp_path: Path):
    console = Console(stderr=True, force_terminal=False, record=True)
    p = RunProgress(console, quiet=True)
    p.start_document(tmp_path / "doc.txt")
    p.substep("hidden")
    p.done_document("summary")
    text = console.export_text().strip()
    assert text == ""


def test_callback_forwards():
    console = Console(stderr=True, force_terminal=False, record=True)
    p = RunProgress(console)
    p.start_document("x.txt")
    cb = p.as_callback()
    cb("Patterns & heuristics…")
    assert "Patterns" in console.export_text()
