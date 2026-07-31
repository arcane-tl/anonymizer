"""Ensure default anonymization does not call remote network APIs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import DocumentAnonymizer
from anonymizer.extract.text import extract_text_file


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
