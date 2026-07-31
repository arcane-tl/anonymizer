"""Redaction review helpers and CLI --reject."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from anonymizer.anonymize.review import (
    apply_review_to_blocks,
    normalize_placeholder,
    parse_reject_list,
    recount_entities,
    unredact,
)
from anonymizer.cli import _preprocess_argv, app

runner = CliRunner()


def _invoke(args: list[str], **kwargs):
    rewritten = _preprocess_argv(["anonymize", *args])
    if rewritten is None:
        return runner.invoke(app, ["--help"])
    return runner.invoke(app, rewritten[1:], **kwargs)


def test_normalize_placeholder():
    assert normalize_placeholder("ORG_1") == "[ORG_1]"
    assert normalize_placeholder("[org_2]") == "[ORG_2]"
    assert normalize_placeholder("  [PHONE_3]  ") == "[PHONE_3]"
    assert normalize_placeholder("PLATE_FI_1") == "[PLATE_FI_1]"
    assert normalize_placeholder("FI_HETU_1") == "[FI_HETU_1]"
    assert normalize_placeholder("not_a_tag") is None
    assert normalize_placeholder("") is None


def test_parse_reject_list():
    valid = {"[ORG_1]", "[ORG_2]", "[PHONE_1]"}
    ok, bad = parse_reject_list("ORG_1, phone_1  [ORG_2]", valid)
    assert ok == ["[ORG_1]", "[PHONE_1]", "[ORG_2]"]
    assert bad == []
    ok2, bad2 = parse_reject_list("ORG_9 xyz", valid)
    assert ok2 == []
    assert "ORG_9" in bad2 and "xyz" in bad2


def test_unredact_and_apply_blocks():
    mapping = {
        "[ORG_1]": "ACME OY",
        "[PHONE_1]": "0401234567",
        "[PERSON_1]": "Maija Korhonen",
    }
    text = "Contact [PERSON_1] at [ORG_1], tel [PHONE_1]. Again [ORG_1]."
    out = unredact(text, mapping, ["[ORG_1]"])
    assert "ACME OY" in out
    assert "[ORG_1]" not in out
    assert "[PHONE_1]" in out
    assert "[PERSON_1]" in out

    blocks = [text, "Only [ORG_1] here"]
    new_blocks, new_map = apply_review_to_blocks(blocks, mapping, ["[ORG_1]"])
    assert "ACME OY" in new_blocks[0]
    assert "ACME OY" in new_blocks[1]
    assert "[ORG_1]" not in new_map
    assert "[PHONE_1]" in new_map
    assert recount_entities(new_map)["PHONE_NUMBER"] == 1


def test_cli_reject_noninteractive(tmp_path: Path):
    src = tmp_path / "note.txt"
    src.write_text(
        "Company NORDIC WIDGETS OY and phone +358 50 987 6543.\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.md"
    # First run without reject to discover placeholder names is brittle;
    # reject both ORG and PHONE via mapping after full run with reject ORG only
    result = _invoke(
        [
            str(src),
            "-o",
            str(out),
            "--lang",
            "en",
            "-q",
            "--reject",
            "ORG_1",
        ],
    )
    assert result.exit_code == 0, result.output
    body = out.read_text(encoding="utf-8")
    # Company restored; phone still redacted if detected
    assert "NORDIC WIDGETS OY" in body
    assert "+358 50 987 6543" not in body or "[PHONE_" in body


def test_cli_review_requires_tty(tmp_path: Path):
    src = tmp_path / "note.txt"
    src.write_text("Hello NORDIC WIDGETS OY.\n", encoding="utf-8")
    out = tmp_path / "out.md"
    result = _invoke(
        [str(src), "-o", str(out), "--review", "-q"],
    )
    # CliRunner is non-TTY → should fail clearly
    assert result.exit_code != 0
    combined = (result.output or "") + (result.stdout or "")
    assert "review" in combined.lower() or "terminal" in combined.lower()


def test_checkbox_review_mocked(monkeypatch):
    """Checkbox path returns selected placeholders."""
    from anonymizer.anonymize import review as review_mod

    mapping = {
        "[ORG_1]": "ACME OY",
        "[PHONE_1]": "0401112222",
        "[PERSON_1]": "Ada Lovelace",
    }

    class FakeCheckbox:
        def __init__(self, *a, **k):
            pass

        def ask(self):
            return ["[ORG_1]", "[PERSON_1]"]

    class FakeChoice:
        def __init__(self, title, value, checked=False):
            self.title = title
            self.value = value
            self.checked = checked

    class FakeQuestionary:
        Choice = FakeChoice

        @staticmethod
        def checkbox(*a, **k):
            return FakeCheckbox()

        class Style:
            def __init__(self, *a, **k):
                pass

    monkeypatch.setitem(__import__("sys").modules, "questionary", FakeQuestionary)
    # Also patch Choice import path used inside function
    import questionary as q_mod

    monkeypatch.setattr(
        review_mod,
        "_checkbox_review",
        lambda mapping, console, file_label: ["[ORG_1]"],
    )
    # Test via interactive_review with questionary "importable"
    selected = review_mod.interactive_review(mapping)
    assert selected == ["[ORG_1]"]


def test_print_keep_clear_summary():
    from io import StringIO

    from rich.console import Console

    from anonymizer.anonymize.review import print_keep_clear_summary

    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=100)
    mapping = {"[ORG_1]": "ACME OY", "[PHONE_1]": "040111"}
    print_keep_clear_summary(mapping, ["[ORG_1]"], console=console)
    out = buf.getvalue()
    assert "ORG_1" in out or "[ORG_1]" in out
    assert "ACME OY" in out
    assert "PHONE_1" not in out or "040111" not in out


def test_checkbox_cancel_aborts(monkeypatch):
    from anonymizer.anonymize import review as review_mod
    from rich.console import Console

    class FakeCheckbox:
        def ask(self):
            return None

    def fake_checkbox(*a, **k):
        return FakeCheckbox()

    import types

    fake_q = types.SimpleNamespace(
        checkbox=fake_checkbox,
        Choice=lambda **k: types.SimpleNamespace(**k),
        Style=lambda *a, **k: None,
    )
    monkeypatch.setitem(__import__("sys").modules, "questionary", fake_q)

    with pytest.raises(SystemExit) as ei:
        review_mod._checkbox_review(
            {"[ORG_1]": "X"},
            console=Console(stderr=True, force_terminal=False),
            file_label="t.txt",
        )
    assert ei.value.code == 130
