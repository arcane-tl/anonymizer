"""Contract hereinafter / myöhemmin company alias learning."""

from __future__ import annotations

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import DocumentAnonymizer
from anonymizer.anonymize.org_stems import (
    find_org_alias_bindings,
    find_org_aliases_in_text,
    usable_org_alias,
)
from presidio_analyzer import RecognizerResult


def test_usable_alias_rejects_roles():
    assert usable_org_alias("Demofirma")
    assert not usable_org_alias("Asiakas")
    assert not usable_org_alias("Toimittaja")
    assert not usable_org_alias("Customer")
    assert not usable_org_alias("the Company")
    assert not usable_org_alias("Oy")
    assert not usable_org_alias("2020")


def test_find_aliases_cue_paren_and_inline():
    text = (
        "Osapuoli Oy Demofirma Ab (myöhemmin Demofirma) sitoutuu. "
        "Toinen Firma Oy myöhemmin FirmaX tekee."
    )
    # Synthetic ORG spans for nearest-primary binding
    results = [
        RecognizerResult(entity_type="ORG", start=text.index("Oy Demofirma Ab"), end=text.index("Oy Demofirma Ab") + len("Oy Demofirma Ab"), score=0.9),
        RecognizerResult(entity_type="ORG", start=text.index("Toinen Firma Oy"), end=text.index("Toinen Firma Oy") + len("Toinen Firma Oy"), score=0.9),
    ]
    aliases = {a.casefold() for a in find_org_aliases_in_text(text, results)}
    assert "demofirma" in aliases
    assert "firmax" in aliases


def test_bare_paren_requires_token_overlap():
    text = "Demofirma Oy (Demofirma) ja Demo Oy (2020) sekä Demo Oy (EU)."
    results: list[RecognizerResult] = []
    start = 0
    for surf in ("Demofirma Oy", "Demo Oy", "Demo Oy"):
        idx = text.index(surf, start)
        results.append(
            RecognizerResult(
                entity_type="ORG", start=idx, end=idx + len(surf), score=0.9
            )
        )
        start = idx + 1
    aliases = {a.casefold() for a in find_org_aliases_in_text(text, results)}
    assert "demofirma" in aliases
    assert "2020" not in aliases
    assert "eu" not in aliases


def test_role_alias_not_learned():
    text = "Demo Services Oy (jäljempänä Asiakas). Asiakas maksaa."
    results = [
        RecognizerResult(
            entity_type="ORG",
            start=text.index("Demo Services Oy"),
            end=text.index("Demo Services Oy") + len("Demo Services Oy"),
            score=0.9,
        )
    ]
    assert find_org_aliases_in_text(text, results) == []
    bindings = find_org_alias_bindings(text, results)
    assert bindings == []


def test_end_to_end_myohemmin_hard_redacts_alias():
    text = (
        "Oy Demofirma Ab (myöhemmin Demofirma) sitoutuu toimittamaan. "
        "Demofirma vastaa viivästyksistä. Demofirman vastuu on rajattu."
    )
    cfg = AnonymizerConfig(mode="strict", lang="fi")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    assert "Demofirma" not in r.anonymized_text
    assert "Demofirman" not in r.anonymized_text
    assert "[ORG_" in r.anonymized_text


def test_end_to_end_inline_and_bare_paren():
    text = (
        "Nordicwidgets Oy myöhemmin Nordicwidgets sitoutuu. "
        "Nordicwidgets Oy (Nordicwidgets) mainitaan uudelleen."
    )
    cfg = AnonymizerConfig(mode="strict", lang="fi")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    assert "Nordicwidgets" not in r.anonymized_text


def test_end_to_end_hereinafter_en():
    text = (
        'Acme Holdings Ltd (hereinafter "Acme"). Acme shall deliver the goods.'
    )
    cfg = AnonymizerConfig(mode="strict", lang="en")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="en")
    assert "Acme Holdings Ltd" not in r.anonymized_text
    assert "Acme" not in r.anonymized_text
    assert "[ORG_" in r.anonymized_text


def test_asiakas_role_not_redacted_as_alias():
    text = (
        "Demo Services Oy (jäljempänä Asiakas) tekee tilauksen. "
        "Asiakas maksaa laskun ajallaan."
    )
    cfg = AnonymizerConfig(mode="strict", lang="fi")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    assert "Asiakas" in r.anonymized_text
    assert not any(v == "Asiakas" for v in r.mapping.values())
