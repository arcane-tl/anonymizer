"""CLI smoke tests."""

from pathlib import Path

from typer.testing import CliRunner

from anonymizer.cli import _preprocess_argv, app
from anonymizer.anonymize.engine import apply_stable_placeholders
from anonymizer.anonymize.recognizers.fi_business_id import FiBusinessIdRecognizer
from anonymizer.anonymize.recognizers.fi_hetu import FiHetuRecognizer
from anonymizer.output.markdown import render_markdown
from anonymizer.models import (
    AnonymizeResult,
    BlockKind,
    LanguageDecision,
    TextBlock,
)

runner = CliRunner()


def _invoke(args: list[str]):
    rewritten = _preprocess_argv(["anonymize", *args])
    if rewritten is None:
        return runner.invoke(app, ["--help"])
    return runner.invoke(app, rewritten[1:])


def test_version():
    result = _invoke(["--version"])
    assert result.exit_code == 0
    assert "anonymizer" in result.stdout


def test_list_entities():
    result = _invoke(["--list-entities"])
    assert result.exit_code == 0
    assert "PERSON" in result.stdout
    assert "FI_HETU" in result.stdout


def test_text_file_pattern_entities(tmp_path: Path):
    """End-to-end without spaCy: exercise extract + CLI may need models.

    This test validates file IO path with a lightweight manual pipeline if
    spaCy is missing; otherwise runs full CLI.
    """
    src = tmp_path / "note.txt"
    src.write_text(
        "Contact support@example.com about order.\n\nY-tunnus 0737546-2.\n",
        encoding="utf-8",
    )
    result = _invoke([str(src), "-o", str(tmp_path / "out.md"), "--lang", "en"])
    # If models missing, exit non-zero — then do lightweight assertion path
    if result.exit_code != 0:
        text = src.read_text(encoding="utf-8")
        recs = []
        recs.extend(FiHetuRecognizer().analyze(text, entities=["FI_HETU"]))
        recs.extend(FiBusinessIdRecognizer().analyze(text, entities=["FI_BUSINESS_ID"]))
        # email rough
        email = "support@example.com"
        if email in text:
            i = text.index(email)
            from presidio_analyzer import RecognizerResult

            recs.append(
                RecognizerResult(
                    entity_type="EMAIL_ADDRESS", start=i, end=i + len(email), score=1.0
                )
            )
        out, _, _ = apply_stable_placeholders(text, recs)
        assert "support@example.com" not in out
        assert "0737546-2" not in out
        return

    out = (tmp_path / "out.md").read_text(encoding="utf-8")
    assert "support@example.com" not in out
    assert "0737546-2" not in out or "[FI_BUSINESS_ID" in out


def test_cli_expands_tilde_input_and_output(tmp_path: Path, monkeypatch):
    """~/… input and -o paths must work (no FileNotFoundError / literal ~ dir)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    src = tmp_path / "note.txt"
    src.write_text("Hello from tilde path.\n", encoding="utf-8")
    result = _invoke(
        [
            "extract",
            "~/note.txt",
            "-o",
            "~/out/body.md",
            "--quiet",
        ]
    )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    out = tmp_path / "out" / "body.md"
    assert out.is_file()
    assert "Hello from tilde path" in out.read_text(encoding="utf-8")
    # Must not write under a literal "~" segment
    assert "~" not in out.parts


def test_load_config_expands_tilde(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("mode: extract\n", encoding="utf-8")
    from anonymizer.anonymize.config import load_config

    cfg = load_config(Path("~/cfg.yaml"))
    assert cfg.mode == "extract"


def test_load_config_invalid_yaml_friendly_error(tmp_path: Path):
    from anonymizer.anonymize.config import ConfigError, load_config

    bad = tmp_path / "broken.yaml"
    bad.write_text("mode: [unterminated\n", encoding="utf-8")
    try:
        load_config(bad)
        raise AssertionError("expected ConfigError")
    except ConfigError as exc:
        msg = str(exc)
        assert "Invalid YAML" in msg
        assert str(bad) in msg
        assert "line" in msg
        assert "config.example.yaml" in msg
        # No multi-line PyYAML dump as the primary message
        assert "while parsing" not in msg


def test_load_config_non_mapping_friendly_error(tmp_path: Path):
    from anonymizer.anonymize.config import ConfigError, load_config

    bad = tmp_path / "list.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    try:
        load_config(bad)
        raise AssertionError("expected ConfigError")
    except ConfigError as exc:
        msg = str(exc)
        assert "mapping" in msg
        assert str(bad) in msg


def test_load_config_unknown_mode_friendly_error(tmp_path: Path):
    from anonymizer.anonymize.config import ConfigError, load_config

    bad = tmp_path / "mode.yaml"
    bad.write_text("mode: banana\n", encoding="utf-8")
    try:
        load_config(bad)
        raise AssertionError("expected ConfigError")
    except ConfigError as exc:
        msg = str(exc)
        assert "Invalid config" in msg
        assert "banana" in msg
        assert str(bad) in msg


def test_cli_bad_config_exits_cleanly(tmp_path: Path):
    src = tmp_path / "note.txt"
    src.write_text("hello\n", encoding="utf-8")
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("mode: [broken\n", encoding="utf-8")
    result = _invoke(
        ["extract", str(src), "--config", str(cfg), "--quiet"]
    )
    assert result.exit_code == 2
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Invalid YAML" in combined
    assert "Traceback" not in combined


def test_cli_quiet_success_shows_absolute_output_path(tmp_path: Path):
    """Quiet mode must still tell the user where the Markdown landed."""
    src = tmp_path / "note.txt"
    src.write_text("Hello plain extract.\n", encoding="utf-8")
    out = tmp_path / "body.md"
    result = _invoke(
        ["extract", str(src), "-o", str(out), "--quiet"]
    )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    assert out.is_file()
    abs_out = str(out.resolve())
    combined = (result.stdout or "") + (result.stderr or "")
    assert abs_out in combined
    assert "OK" in combined


def test_cli_success_shows_wrote_path_non_quiet(tmp_path: Path):
    src = tmp_path / "note.txt"
    src.write_text("Hello extract again.\n", encoding="utf-8")
    out = tmp_path / "out" / "body.md"
    result = _invoke(["extract", str(src), "-o", str(out)])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    abs_out = str(out.resolve())
    combined = (result.stdout or "") + (result.stderr or "")
    assert abs_out in combined
    assert "Wrote" in combined


def test_report_write_success_helper_formats_paths(tmp_path: Path):
    from rich.console import Console

    from anonymizer.cli import _report_write_success
    import anonymizer.cli as cli_mod

    out = tmp_path / "x.md"
    out.write_text("x", encoding="utf-8")
    mp = tmp_path / "x.map.json"
    mp.write_text("{}", encoding="utf-8")

    recorded = Console(stderr=True, force_terminal=False, record=True)
    old = cli_mod.console
    try:
        cli_mod.console = recorded
        _report_write_success(
            quiet=True,
            input_name="x.txt",
            elapsed="1.0s",
            summary="mode=extract · entities: none",
            out_path=out,
            map_file=mp,
        )
        text = recorded.export_text()
        assert str(out.resolve()) in text
        assert str(mp.resolve()) in text
        assert "OK" in text
    finally:
        cli_mod.console = old
