"""Ensure default anonymization does not call remote network APIs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import DocumentAnonymizer
from anonymizer.anonymize.llm import is_loopback_url
from anonymizer.cli import app
from anonymizer.extract.text import extract_text_file
from anonymizer.lists_io import load_lists


def test_default_path_does_not_call_remote_llm():
    """use_llm=False must never open remote HTTP or openai client."""
    path = Path(__file__).parent / "fixtures" / "contract_en.txt"
    doc = extract_text_file(path)
    blocks = [b.text for b in doc.blocks]

    def boom_urlopen(*_a, **_k):
        raise AssertionError("urllib urlopen must not be called offline")

    def boom_openai(*_a, **_k):
        raise AssertionError("OpenAI client must not be constructed offline")

    with patch("urllib.request.urlopen", side_effect=boom_urlopen):
        with patch.dict("sys.modules", {"openai": type(pytest)("openai")}):
            # If openai imported and client built, fail via custom
            import anonymizer.anonymize.llm as llm_mod

            with patch.object(llm_mod, "_call_xai", side_effect=boom_openai):
                with patch.object(llm_mod, "_call_ollama", side_effect=boom_openai):
                    cfg = AnonymizerConfig(lang="en", use_llm=False)
                    out, res = DocumentAnonymizer(cfg).anonymize_blocks(
                        blocks, lang_flag="en"
                    )
    assert out
    assert res.entity_counts is not None


def test_llm_module_not_invoked_when_disabled(monkeypatch):
    called = {"n": 0}

    def fake_llm(*_a, **_k):
        called["n"] += 1
        return []

    monkeypatch.setattr(
        "anonymizer.anonymize.llm.llm_entity_results",
        fake_llm,
        raising=False,
    )
    # Patch at use site
    import anonymizer.anonymize.engine as eng

    monkeypatch.setattr(
        eng,
        "DocumentAnonymizer",
        eng.DocumentAnonymizer,
    )
    path = Path(__file__).parent / "fixtures" / "contract_en.txt"
    text = extract_text_file(path).full_text()[:2000]
    cfg = AnonymizerConfig(use_llm=False, lang="en")
    DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="en")
    # llm_entity_results only imported inside if use_llm — ensure not called
    assert called["n"] == 0


def test_is_loopback_url() -> None:
    assert is_loopback_url("http://127.0.0.1:11434")
    assert is_loopback_url("http://localhost:11434")
    assert not is_loopback_url("http://evil.example:11434")
    assert not is_loopback_url("https://api.x.ai/v1")


def test_yaml_use_llm_ignored_without_cli_flag(tmp_path: Path) -> None:
    """Config use_llm:true must not enable LLM without --llm (H1)."""
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        "use_llm: true\nllm_provider: xai\n",
        encoding="utf-8",
    )
    fixture = Path(__file__).parent / "fixtures" / "contract_en.txt"
    runner = CliRunner()
    with patch("urllib.request.urlopen", side_effect=AssertionError("no network")):
        result = runner.invoke(
            app,
            [str(fixture), "--config", str(cfg_path), "-q", "-o", str(tmp_path / "o.md")],
        )
    assert result.exit_code == 0, result.output
    assert "use_llm" in result.output or result.exit_code == 0


def test_offline_blocks_remote_ollama(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "contract_en.txt"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            str(fixture),
            "--llm",
            "--llm-provider",
            "ollama",
            "--offline",
            "-q",
            "-o",
            str(tmp_path / "o.md"),
        ],
        env={**dict(**__import__("os").environ), "ANONYMIZER_TEST": "1"},
    )
    # May fail on missing models in CI path; if config ollama is default local it may pass.
    # Force non-local via config:
    cfg = tmp_path / "remote.yaml"
    cfg.write_text(
        "use_llm: true\nllm_provider: ollama\nollama_url: http://evil.example:11434\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            str(fixture),
            "--llm",
            "--config",
            str(cfg),
            "--offline",
            "-q",
            "-o",
            str(tmp_path / "o2.md"),
        ],
    )
    assert result.exit_code == 2
    assert "offline" in result.output.lower() or "non-local" in result.output.lower()


def test_empty_allowlist_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("allowlist: []\ndenylist: []\n", encoding="utf-8")
    monkeypatch.setenv("ANONYMIZER_CONFIG", str(cfg))
    allow, deny = load_lists(cfg)
    assert allow == []
    assert deny == []
