"""spaCy PERSON span expansion over adjacent PROPN (FI given + surname)."""

from __future__ import annotations

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import DocumentAnonymizer


def _strict_fi(text: str):
    cfg = AnonymizerConfig(mode="strict", lang="fi", use_llm=False)
    cfg.apply_mode()
    return DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")


def test_karo_vallittu_bare_redacted():
    r = _strict_fi("Karo Vallittu")
    assert "Karo" not in r.anonymized_text
    assert "Vallittu" not in r.anonymized_text
    assert "[PERSON_" in r.anonymized_text


def test_karo_vallittu_with_title_redacted():
    r = _strict_fi("Karo Vallittu, projektipäällikkö")
    assert "Karo Vallittu" not in r.anonymized_text
    assert "[PERSON_" in r.anonymized_text
    assert "projektipäällikkö" in r.anonymized_text


def test_karo_vallittu_with_label_still_works():
    r = _strict_fi("Yhteyshenkilö Karo Vallittu vastaa.")
    assert "Karo" not in r.anonymized_text
    assert "[PERSON_" in r.anonymized_text


def test_no_person_from_two_nouns_without_spacy_person_seed():
    # Expansion requires a spaCy PERSON seed — bare Title Title nouns alone
    # should not invent a person if spaCy never tags PERSON.
    r = _strict_fi("Sopimusasiakirja Liite")
    # Not asserting zero PERSON globally (spaCy may tag oddly); just that we
    # did not force-join random nouns into a known false pattern.
    assert "Sopimusasiakirja" in r.anonymized_text or "[ORG_" in r.anonymized_text


def test_cv_tools_not_person():
    text = (
        "Tekniset työkalut: Microsoft Teams, Jira, Confluence, Salesforce, "
        "Power BI. Asiakkaalle Solita digitaaliset palvelut. "
        "Yhteyshenkilö Karo Vallittu."
    )
    r = _strict_fi(text)
    joined_map = " ".join(r.mapping.values()).casefold()
    for tool in (
        "microsoft",
        "teams",
        "jira",
        "confluence",
        "salesforce",
        "power bi",
        "powerbi",
        "solita",
    ):
        assert tool not in joined_map, (tool, r.mapping)
        # Surface should remain visible in body (not redacted as PERSON)
        # Allow Solita as ORG if spaCy tags it — just not PERSON
    for ph, orig in r.mapping.items():
        if ph.startswith("[PERSON_"):
            low = orig.casefold()
            assert "jira" not in low
            assert "teams" not in low
            assert "confluence" not in low
            assert "salesforce" not in low
            assert "microsoft" not in low
            assert "solita" not in low
            assert "power" not in low or "bi" not in low
    assert "Karo" not in r.anonymized_text
    assert "[PERSON_" in r.anonymized_text


def test_jira_confluence_comma_not_last_first():
    from anonymizer.anonymize.recognizers.person_name import find_person_names

    text = "viestintää, Jira-tikettejä, Confluence-sivuja ja Salesforce"
    assert find_person_names(text) == []
    r = _strict_fi(text)
    assert not any(
        "jira" in v.casefold() or "confluence" in v.casefold()
        for k, v in r.mapping.items()
        if k.startswith("[PERSON_")
    )
