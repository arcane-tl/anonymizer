"""Run summary sidecar (not embedded in Markdown)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from anonymizer.output.run_summary import (
    RunSummary,
    format_summaries_plain,
    load_summaries,
    write_summary_if_requested,
)


def test_run_summary_plain_and_markdown(tmp_path: Path) -> None:
    s = RunSummary(
        source="/tmp/demo.pdf",
        mode="strict",
        entity_counts={"PERSON": 2, "ORG": 1},
        outputs=[
            {
                "kind": "markdown",
                "path": str(tmp_path / "demo.anonymized.md"),
                "source_metadata_carried": False,
            }
        ],
        native={"native_clean": True, "native_residuals": 0},
    )
    plain = s.to_plain_text()
    assert "PERSON=2" in plain
    assert "Native clean: True" in plain
    assert "rebuild" in plain

    md = s.to_markdown()
    assert "# Anonymizer run summary" in md
    assert "`PERSON`" in md

    out = s.save(tmp_path / "demo.anonymizer-summary.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["mode"] == "strict"
    assert data["entity_counts"]["PERSON"] == 2


def test_write_summary_if_requested_appends_array(
    tmp_path: Path, monkeypatch
) -> None:
    dest = tmp_path / "batch.json"
    monkeypatch.setenv("ANONYMIZER_WRITE_SUMMARY_JSON", str(dest))

    a = RunSummary(source="a.txt", mode="strict", entity_counts={"PERSON": 1})
    b = RunSummary(source="b.txt", mode="standard", entity_counts={"EMAIL": 1})
    assert write_summary_if_requested(a) == dest
    assert write_summary_if_requested(b) == dest

    items = load_summaries(dest)
    assert len(items) == 2
    assert items[0]["source"] == "a.txt"
    assert items[1]["mode"] == "standard"

    plain = format_summaries_plain(items)
    assert "File 1" in plain
    assert "File 2" in plain


def test_write_summary_skipped_without_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ANONYMIZER_WRITE_SUMMARY_JSON", raising=False)
    s = RunSummary(source="x.txt", mode="extract")
    assert write_summary_if_requested(s) is None
    assert list(tmp_path.iterdir()) == []


def test_cli_writes_summary_json_when_env_set(
    tmp_path: Path, monkeypatch
) -> None:
    from typer.testing import CliRunner

    from anonymizer.cli import _preprocess_argv, app

    src = tmp_path / "note.txt"
    src.write_text("Hello Alice Example.\n", encoding="utf-8")
    summary = tmp_path / "sum.json"
    monkeypatch.setenv("ANONYMIZER_WRITE_SUMMARY_JSON", str(summary))

    runner = CliRunner()
    argv = [
        "anonymize",
        "extract",
        str(src),
        "-o",
        str(tmp_path / "note.md"),
        "-q",
    ]
    rewritten = _preprocess_argv(argv)
    assert rewritten is not None
    result = runner.invoke(app, rewritten[1:])
    assert result.exit_code == 0, result.output
    assert summary.is_file()
    items = json.loads(summary.read_text(encoding="utf-8"))
    assert isinstance(items, list)
    assert items[0]["mode"] == "extract"
    assert items[0]["source"].endswith("note.txt")
    # Markdown body must stay free of run-report YAML
    md = (tmp_path / "note.md").read_text(encoding="utf-8")
    assert not md.lstrip().startswith("---")
    assert "entity_counts:" not in md


def test_show_summary_print(tmp_path: Path, capsys) -> None:
    from anonymizer.cli import cmd_show_summary

    payload = [
        {
            "source": "a.txt",
            "mode": "strict",
            "tool_version": "1.4.7",
            "anonymized_at": "2026-01-01T00:00:00Z",
            "entity_counts": {"PERSON": 1},
            "outputs": [],
        }
    ]
    path = tmp_path / "s.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    cmd_show_summary([str(path), "--print"])
    out = capsys.readouterr().out
    assert "PERSON=1" in out
    assert "a.txt" in out
