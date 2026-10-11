"""Tests for runtime progress helper."""

import json
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


def test_phase_for_message():
    from anonymizer.util.progress import phase_for_message

    assert phase_for_message("Review redactions…") == "Waiting for review"
    assert phase_for_message("Reading PDF text layer…") == "Reading the document"
    assert phase_for_message("Neural NER (fi)…") == "Finding sensitive data"
    assert phase_for_message("Writing native out.pdf…") == "Writing files"


def test_quiet_still_writes_status(tmp_path: Path, monkeypatch):
    dest = tmp_path / "status.json"
    monkeypatch.setenv("ANONYMIZER_PROGRESS_FILE", str(dest))
    monkeypatch.setenv("ANONYMIZER_PROGRESS_INDEX", "2")
    monkeypatch.setenv("ANONYMIZER_PROGRESS_TOTAL", "4")
    console = Console(stderr=True, force_terminal=False, record=True)
    p = RunProgress(console, quiet=True)
    p.start_document(tmp_path / "cv.pdf", 1, 1)
    p.substep("Neural NER (en)…")
    p.done_document("entities: 3")
    assert console.export_text().strip() == ""
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["state"] == "running"
    assert data["phase"] == "Finding sensitive data"
    assert data["index"] == 2
    assert data["total"] == 4
    assert data["file"] == "cv.pdf"
    # File 2 of 4 finished: bar sits at the end of that file, job still running.
    assert data["fraction"] == 0.5


def test_substep_fraction_is_within_file(tmp_path: Path):
    dest = tmp_path / "status.json"
    console = Console(stderr=True, force_terminal=False, record=True)
    p = RunProgress(console, quiet=True, status_path=dest)
    p.start_document("a.pdf", 2, 4)
    p.substep("Patterns & heuristics…")
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["phase"] == "Finding sensitive data"
    # File 2 of 4, finding sits at 0.6 through that file.
    assert abs(data["fraction"] - ((2 - 1) + 0.6) / 4) < 1e-6
    assert not dest.with_name(dest.name + ".tmp").exists()


def test_callback_forwards():
    console = Console(stderr=True, force_terminal=False, record=True)
    p = RunProgress(console)
    p.start_document("x.txt")
    cb = p.as_callback()
    cb("Patterns & heuristics…")
    assert "Patterns" in console.export_text()
