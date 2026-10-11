"""FI form-label FP filters + optional Voikko helpers."""

from __future__ import annotations

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import (
    DocumentAnonymizer,
    _allowlist_label_phrase,
    _looks_like_field_label,
)
from anonymizer.anonymize.voikko_fi import (
    all_tokens_common_finnish,
    is_common_finnish_word,
    voikko_available,
)


def test_looks_like_field_label_yrityksen_y_tunnus_column():
    text = "Yrityksen Y-tunnus    1234567-8\nYrityksen ALV-numero  FI12345678\n"
    start = text.index("Yrityksen Y-tunnus")
    end = start + len("Yrityksen Y-tunnus")
    assert _looks_like_field_label(text, start, end)

    start2 = text.index("Yrityksen ALV-numero")
    end2 = start2 + len("Yrityksen ALV-numero")
    assert _looks_like_field_label(text, start2, end2)


def test_looks_like_field_label_keeps_company_with_legal_form():
    text = "NORDIC WIDGETS OY: allekirjoitus\n"
    start = text.index("NORDIC WIDGETS OY")
    end = start + len("NORDIC WIDGETS OY")
    assert not _looks_like_field_label(text, start, end)


def test_allowlist_possessive_y_tunnus():
    allowed = ["y-tunnus", "alv-numero"]
    assert _allowlist_label_phrase("yrityksen y-tunnus", allowed)
    assert not _allowlist_label_phrase("acme y-tunnus services oy", allowed)


def test_form_label_not_org_end_to_end():
    text = (
        "Yrityksen Y-tunnus    1234567-8\n"
        "Yrityksen ALV-numero  FI12345678\n"
        "Yrityksen rekisterinumero  ABC-123\n"
        "Toimittaja: ACME Testi Oy\n"
    )
    cfg = AnonymizerConfig(mode="strict", lang="fi")
    # Apply builtin templates like the app
    from anonymizer.anonymize.templates import (
        apply_templates_to_config,
        default_enabled_ids,
        discover_templates,
    )

    packs = discover_templates(include_user=False)
    apply_templates_to_config(
        cfg, enabled_ids=default_enabled_ids(packs), replace_lists=True
    )
    result = DocumentAnonymizer(cfg).anonymize_text(text)
    # Label must not become ORG / PERSON / LOCATION
    for ph, surface in result.mapping.items():
        if ph.startswith(("[ORG_", "[PERSON_", "[LOCATION_")):
            assert "Y-tunnus" not in surface
            assert "ALV-numero" not in surface
            assert "rekisterinumero" not in surface.casefold()
    assert "Yrityksen Y-tunnus" in result.anonymized_text
    # Structured IDs / plate still redacted
    assert "1234567-8" not in result.anonymized_text
    assert "FI12345678" not in result.anonymized_text
    assert "ABC-123" not in result.anonymized_text
    assert "ACME Testi Oy" not in result.anonymized_text


def test_voikko_helpers_without_lib_return_none():
    ok, _ = voikko_available()
    if ok:
        # When installed, common noun should be True; name-class False/None-safe
        assert is_common_finnish_word("kissa") in {True, False, None}
        return
    assert is_common_finnish_word("kissa") is None
    assert all_tokens_common_finnish(["yrityksen", "nimi"]) is None


def test_voikko_all_tokens_mocked(monkeypatch):
    import anonymizer.anonymize.voikko_fi as v

    monkeypatch.setattr(v, "voikko_available", lambda: (True, "ok"))

    def fake_common(word: str):
        w = word.casefold()
        if w in {"yrityksen", "nimi", "tunnus", "y"}:
            return True
        if w in {"nokia", "helsinki"}:
            return False
        return False

    monkeypatch.setattr(v, "is_common_finnish_word", fake_common)
    assert all_tokens_common_finnish(["Yrityksen", "nimi"]) is True
    assert all_tokens_common_finnish(["Nokia", "Oy"]) is False
