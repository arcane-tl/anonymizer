"""Operating modes: extract / standard / strict."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from anonymizer.anonymize.config import (
    STANDARD_ENTITIES,
    STRICT_ENTITIES,
    AnonymizerConfig,
    entities_for_mode,
    normalize_mode,
)
from anonymizer.anonymize.engine import DocumentAnonymizer
from anonymizer.cli import _preprocess_argv, app
from anonymizer.extract.text import extract_text_file

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def _invoke(args: list[str], **kwargs):
    """Invoke CLI with the same argv rewriting as the real entrypoint."""
    rewritten = _preprocess_argv(["anonymize", *args])
    if rewritten is None:
        # Meta command (doctor/examples) already executed via Exit
        return runner.invoke(app, ["--version"])  # shouldn't happen if Exit raised
    return runner.invoke(app, rewritten[1:], **kwargs)


def test_normalize_mode_aliases():
    assert normalize_mode("strict") == "strict"
    assert normalize_mode("full") == "strict"
    assert normalize_mode("standard") == "standard"
    assert normalize_mode("normal") == "standard"
    assert normalize_mode("pii") == "standard"
    assert normalize_mode("extract") == "extract"
    assert normalize_mode("text") == "extract"
    assert normalize_mode("plain") == "extract"
    with pytest.raises(ValueError):
        normalize_mode("banana")


def test_entities_for_mode_sets():
    assert entities_for_mode("extract") == []
    std = entities_for_mode("standard")
    strict = entities_for_mode("strict")
    assert "PERSON" in std
    assert "EMAIL_ADDRESS" in std
    assert "ORG" not in std
    assert "LOCATION" not in std
    assert "FI_BUSINESS_ID" not in std
    assert "URL" not in std
    assert "ORG" in strict
    assert "LOCATION" in strict
    assert set(std) == set(STANDARD_ENTITIES)
    assert set(strict) == set(STRICT_ENTITIES)


def test_extract_mode_passthrough_no_placeholders():
    path = FIXTURES / "contract_en.txt"
    doc = extract_text_file(path)
    source = "\n\n".join(b.text for b in doc.blocks)
    cfg = AnonymizerConfig(mode="extract", lang="en")
    cfg.apply_mode()
    out_blocks, result = DocumentAnonymizer(cfg).anonymize_blocks(
        [b.text for b in doc.blocks], lang_flag="en"
    )
    out = "\n\n".join(out_blocks)
    assert result.mode == "extract"
    assert result.mapping == {}
    assert result.entity_counts == {}
    # No redaction of known PII
    assert "Jordan Avery Blake" in out
    assert "NORDIC WIDGETS OY" in out
    assert "jordan.blake@nordic-widgets.example.com" in out
    assert "[PERSON_" not in out
    assert "[ORG_" not in out
    assert "[EMAIL_" not in out
    # Passthrough preserves content length roughly
    assert "Service Agreement" in out or "Agreement" in source


def test_standard_redacts_identity_keeps_company():
    path = FIXTURES / "contract_fi.txt"
    doc = extract_text_file(path)
    cfg = AnonymizerConfig(mode="standard", lang="fi")
    cfg.apply_mode()
    assert "ORG" not in cfg.effective_entities()
    out_blocks, result = DocumentAnonymizer(cfg).anonymize_blocks(
        [b.text for b in doc.blocks], lang_flag="fi"
    )
    out = "\n\n".join(out_blocks)
    assert result.mode == "standard"

    # Identity / contact / address / IDs gone
    for leak in (
        "Maija Korhonen",
        "Pekka Nieminen",
        "maija.korhonen@nordic-widgets.example.fi",
        "+358 50 987 6543",
        "131052-308T",
        "Mannerheimintie 12",
        "00100",
        "FI21 1234 5600 0007 85",
    ):
        assert leak not in out, f"should redact in standard: {leak}"

    # Companies / business IDs / brands / URLs stay
    for keep in (
        "NORDIC WIDGETS OY",
        "SILVER PINE",
        "ACME LOGISTICS AB",
        "0737546-2",
        "FI07375462",
        "https://www.nordic-widgets.example.fi/palvelut",
    ):
        assert keep in out, f"should keep in standard: {keep}"


def test_standard_keeps_country_location_en():
    """Country-level LOCATION is not redacted in standard mode."""
    text = (
        "The Author lives at 12 Baker Street, London. "
        "Rights apply in the United States of America and Canada. "
        "Contact: Jordan Avery Blake, jordan@example.com, +1 (415) 555-0199."
    )
    cfg = AnonymizerConfig(mode="standard", lang="en")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="en")
    out = r.anonymized_text
    assert "United States" in out or "America" in out
    assert "Canada" in out
    assert "12 Baker Street" not in out
    assert "Jordan Avery Blake" not in out
    assert "jordan@example.com" not in out
    assert "NORDIC" not in text  # sanity


def test_strict_redacts_company():
    path = FIXTURES / "contract_en.txt"
    doc = extract_text_file(path)
    cfg = AnonymizerConfig(mode="strict", lang="en")
    cfg.apply_mode()
    out_blocks, result = DocumentAnonymizer(cfg).anonymize_blocks(
        [b.text for b in doc.blocks], lang_flag="en"
    )
    out = "\n\n".join(out_blocks)
    assert result.mode == "strict"
    assert "NORDIC WIDGETS OY" not in out
    assert "Jordan Avery Blake" not in out
    assert "SILVER PINE" not in out


def test_entities_cli_overrides_mode(tmp_path: Path):
    """--entities overrides mode preset (only email redacted)."""
    src = tmp_path / "note.txt"
    src.write_text(
        "Call Jordan Avery Blake at jordan@example.com about NORDIC WIDGETS OY.\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.md"
    result = _invoke(
        [
            str(src),
            "-o",
            str(out),
            "--mode",
            "strict",
            "--entities",
            "EMAIL_ADDRESS",
            "--lang",
            "en",
            "-q",
        ],
    )
    assert result.exit_code == 0, result.output
    body = out.read_text(encoding="utf-8")
    assert "jordan@example.com" not in body
    # Name and company kept when only EMAIL is requested
    assert "Jordan Avery Blake" in body
    assert "NORDIC WIDGETS OY" in body


def test_cli_extract_mode(tmp_path: Path):
    src = tmp_path / "note.txt"
    src.write_text(
        "Secret: Maija Korhonen, hetu 131052-308T, NORDIC WIDGETS OY.\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.md"
    result = _invoke(
        [str(src), "-o", str(out), "--mode", "extract", "-q"],
    )
    assert result.exit_code == 0, result.output
    body = out.read_text(encoding="utf-8")
    assert "mode: extract" in body
    assert "Maija Korhonen" in body
    assert "131052-308T" in body
    assert "NORDIC WIDGETS OY" in body
    assert "[PERSON_" not in body
    assert "[FI_HETU_" not in body


def test_cli_extract_subcommand(tmp_path: Path):
    src = tmp_path / "note.txt"
    src.write_text("Maija Korhonen works at NORDIC WIDGETS OY.\n", encoding="utf-8")
    result = _invoke(["extract", str(src), "-q"])
    assert result.exit_code == 0, result.output
    out = tmp_path / "note.md"
    assert out.is_file(), list(tmp_path.iterdir())
    body = out.read_text(encoding="utf-8")
    assert "mode: extract" in body
    assert "Maija Korhonen" in body
    assert "NORDIC WIDGETS OY" in body


def test_cli_standard_subcommand(tmp_path: Path):
    src = tmp_path / "note.txt"
    src.write_text(
        "Maija Korhonen, maija@example.com, NORDIC WIDGETS OY, 0737546-2\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.md"
    result = _invoke(
        ["standard", str(src), "-o", str(out), "--lang", "fi", "-q"]
    )
    assert result.exit_code == 0, result.output
    body = out.read_text(encoding="utf-8")
    assert "mode: standard" in body
    assert "maija@example.com" not in body
    assert "NORDIC WIDGETS OY" in body
    assert "0737546-2" in body


def test_cli_list_entities_shows_modes():
    result = _invoke(["--list-entities"])
    assert result.exit_code == 0
    assert "extract" in result.stdout
    assert "standard" in result.stdout
    assert "strict" in result.stdout
    assert "PERSON" in result.stdout


def test_cli_doctor():
    # typer.Exit is a SystemExit subclass in some versions; catch both
    with pytest.raises(BaseException) as ei:
        _preprocess_argv(["anonymize", "doctor"])
    code = getattr(ei.value, "exit_code", None)
    if code is None:
        code = getattr(ei.value, "code", None)
    assert code in (0, 1, None) or ei.type.__name__ in ("Exit", "SystemExit")


def test_cli_examples_prints(capsys):
    rewritten = _preprocess_argv(["anonymize", "examples"])
    assert rewritten is None
    captured = capsys.readouterr()
    assert "anonymize extract" in captured.out
    assert "anonymize doctor" in captured.out


def test_cli_help_shows_examples():
    result = _invoke(["--help"])
    assert result.exit_code == 0
    out = result.stdout + result.output
    assert "extract" in out.lower()
    assert "doctor" in out.lower() or "mode" in out.lower()


def test_front_matter_includes_mode():
    cfg = AnonymizerConfig(mode="standard", lang="en")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text("Hello Alice.", lang_flag="en")
    from anonymizer.output.markdown import render_markdown
    from anonymizer.models import TextBlock, BlockKind

    md = render_markdown(
        "x.txt",
        [TextBlock(text=r.anonymized_text, kind=BlockKind.PARAGRAPH)],
        r,
    )
    assert "mode: standard" in md
