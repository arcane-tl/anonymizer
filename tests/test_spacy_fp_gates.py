"""spaCy FP gates: PRODUCT opt-in, language primary, proposals, FP log."""

from __future__ import annotations

from pathlib import Path

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import (
    DocumentAnonymizer,
    _blank_pre_ner_noise,
    _is_pre_ner_skip_line,
    _person_context_ok,
    _spacy_label_map,
)
from anonymizer.anonymize.fp_log import (
    append_fp_reject,
    load_fp_records,
    summarize_fp_records,
)
from anonymizer.anonymize.language import resolve_language


def test_product_not_mapped_by_default():
    assert "PRODUCT" not in _spacy_label_map(map_product_to_org=False)
    assert _spacy_label_map(map_product_to_org=True)["PRODUCT"] == "ORG"


def test_pre_ner_skips_label_lines():
    assert _is_pre_ner_skip_line("Rekisterinumero:")
    assert _is_pre_ner_skip_line("Nimi:")
    assert not _is_pre_ner_skip_line("Maija Virtanen allekirjoitti sopimuksen.")


def test_blank_pre_ner_preserves_offsets():
    text = "Nimi:\nMaija Virtanen\n"
    blanked = _blank_pre_ner_noise(text)
    assert len(blanked) == len(text)
    assert blanked.startswith(" " * len("Nimi:"))
    assert "Maija" in blanked


def test_person_context_requires_neighbor_cue():
    text = "xxx Maija yyy"
    start = text.index("Maija")
    end = start + len("Maija")
    assert not _person_context_ok(text, start, end)
    text2 = "Nimi: Maija"
    start2 = text2.index("Maija")
    assert _person_context_ok(text2, start2, start2 + len("Maija"))


def test_fp_log_roundtrip(tmp_path: Path, monkeypatch):
    log = tmp_path / "fp.jsonl"
    monkeypatch.setenv("ANONYMIZER_FP_LOG", str(log))
    append_fp_reject(
        {
            "entity_type": "PERSON",
            "surface": "Rekisterinumero",
            "placeholder": "[PERSON_1]",
            "sources": ["spacy:fi"],
            "single_token": True,
            "pos": ["PROPN"],
        }
    )
    recs = load_fp_records(log)
    assert len(recs) == 1
    summary = summarize_fp_records(recs)
    assert summary["total"] == 1
    assert summary["spacy_single_token_person"] == 1


def test_form_labels_not_auto_redacted_without_review():
    """FI form labels must not become auto mapping under corroborated policy."""
    text = (
        "Rekisterinumero:\n"
        "Tunniste:\n"
        "Osoite:\n"
        "Yhteyshenkilö:\n"
    )
    cfg = AnonymizerConfig(mode="strict", lang="fi")
    cfg.spacy_auto_redact = "corroborated"
    eng = DocumentAnonymizer(cfg)
    result = eng.anonymize_text(text, lang_flag="fi")
    # No PERSON/ORG placeholders for bare labels in the auto map
    joined = " ".join(result.mapping.values()).casefold()
    assert "rekisterinumero" not in joined
    assert "tunniste" not in joined


def test_multi_token_person_auto_redacts():
    cfg = AnonymizerConfig(mode="strict", lang="en")
    cfg.spacy_auto_redact = "corroborated"
    eng = DocumentAnonymizer(cfg)
    text = "Contact Alice Example at the office today."
    result = eng.anonymize_text(text, lang_flag="en")
    assert "Alice Example" not in result.anonymized_text
    assert any("Alice" in v for v in result.mapping.values())


def test_soft_org_without_legal_form_is_proposal():
    """Capitalised soft ORG without pattern corroboration → proposal, not auto."""
    cfg = AnonymizerConfig(mode="strict", lang="en")
    cfg.spacy_auto_redact = "corroborated"
    eng = DocumentAnonymizer(cfg)
    # Avoid legal-form / brand recognizers; single weak ORG-like span
    text = "Please review the Force Majeure clause carefully before signing."
    result = eng.anonymize_text(text, lang_flag="en")
    assert "Force Majeure" in result.anonymized_text or "Force Majeure" not in (
        result.mapping.values()
    )
    assert "Force Majeure" not in result.mapping.values()
