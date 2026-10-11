"""Soft-hyphen / syllable repair (extract path)."""

from __future__ import annotations

from anonymizer.extract.text_repair import (
    repair_soft_hyphens,
    repair_text_artifacts,
    should_join_soft_hyphen,
    should_keep_compound_hyphen,
)


def test_join_finnish_syllable_breaks():
    assert should_join_soft_hyphen("työ", "kokemus")
    assert should_join_soft_hyphen("kon", "sultointiin")
    assert repair_soft_hyphens("vahvaa työ-kokemus ja kon-sultointiin.") == (
        "vahvaa työkokemus ja konsultointiin."
    )


def test_join_soft_hyphen_across_newline():
    assert (
        repair_soft_hyphens("koko-\nnaistuntimäärään") == "kokonaistuntimäärään"
    )
    assert (
        repair_text_artifacts("lasketaan koko-\nnaistuntimäärään mukaan")
        == "lasketaan kokonaistuntimäärään mukaan"
    )
    # Real compounds: drop the break, keep the hyphen
    assert repair_soft_hyphens("ETA-\nmaat") == "ETA-maat"
    assert repair_soft_hyphens("pre-\nsales") == "pre-sales"


def test_join_title_case_name_syllables():
    """Word wrap in names/companies: Eli-salla → Elisalla for ORG/PERSON NER."""
    assert not should_keep_compound_hyphen("Eli", "salla")
    assert should_join_soft_hyphen("Eli", "salla")
    assert repair_soft_hyphens("Asiakas Eli-salla Oy") == "Asiakas Elisalla Oy"


def test_keep_real_compounds():
    assert should_keep_compound_hyphen("pre", "sales")
    assert should_keep_compound_hyphen("Jira", "tiketin")
    assert should_keep_compound_hyphen("ETA", "maat")
    assert not should_join_soft_hyphen("pre", "sales")
    assert not should_join_soft_hyphen("Jira", "tiketin")
    assert not should_join_soft_hyphen("ETA", "maat")
    text = "pre-sales Jira-tiketin ETA-maat e-mail full-stack"
    assert repair_soft_hyphens(text) == text


def test_strips_unicode_soft_hyphen():
    # U+00AD between syllables
    raw = "työ\u00adkokemus"
    assert repair_soft_hyphens(raw) == "työkokemus"


def test_repair_text_artifacts_runs_without_newline():
    # Previously bailed when no \\n — Word leftovers live in one paragraph
    assert "työkokemus" in repair_text_artifacts("työ-kokemus")
    assert "pre-sales" in repair_text_artifacts("pre-sales")


def test_idempotent():
    once = repair_soft_hyphens("työ-kokemus pre-sales")
    twice = repair_soft_hyphens(once)
    assert once == twice == "työkokemus pre-sales"


def test_does_not_break_hyphenated_domains_or_emails():
    email = "jordan.blake@nordic-widgets.example.com"
    url = "https://www.nordic-widgets.example.fi/palvelut"
    assert repair_soft_hyphens(email) == email
    assert repair_soft_hyphens(url) == url
    assert repair_text_artifacts(email) == email


def test_elisalla_org_after_hyphen_repair():
    from anonymizer.anonymize.config import AnonymizerConfig
    from anonymizer.anonymize.engine import DocumentAnonymizer

    cfg = AnonymizerConfig(mode="strict", lang="fi", use_llm=False)
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(
        "Sopimusosapuoli Eli-salla Oy toimittaa palvelun.",
        lang_flag="fi",
    )
    assert "Eli-salla" not in r.anonymized_text
    assert "Elisalla" not in r.anonymized_text
    assert "[ORG_" in r.anonymized_text
