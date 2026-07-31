"""Finnish phone number recognizer tests."""

from anonymizer.anonymize.engine import apply_stable_placeholders
from anonymizer.anonymize.recognizers.fi_phone import (
    FiPhoneRecognizer,
    find_fi_phones,
    is_plausible_fi_phone,
)


def test_plausible_international():
    assert is_plausible_fi_phone("+358 50 987 6543")
    assert is_plausible_fi_phone("+358501234567")
    assert is_plausible_fi_phone("+358 (0) 40 123 4567")
    assert is_plausible_fi_phone("00358 40 123 4567")


def test_plausible_national():
    assert is_plausible_fi_phone("040 123 4567")
    assert is_plausible_fi_phone("050-987-6543")
    assert is_plausible_fi_phone("0401234567")
    assert is_plausible_fi_phone("09 1234 567")


def test_reject_too_short():
    assert not is_plausible_fi_phone("040 12")
    assert not is_plausible_fi_phone("+358 1")


def test_find_in_sentence():
    text = "Soita Maijalle numeroon +358 50 987 6543 huomenna."
    hits = find_fi_phones(text)
    assert len(hits) == 1
    start, end, value = hits[0]
    assert value == "+358 50 987 6543"
    assert text[start:end] == value


def test_find_national_and_intl():
    text = "A: 040 123 4567 B: +358401234567 C: 09 1234 567"
    hits = find_fi_phones(text)
    values = {h[2] for h in hits}
    assert "040 123 4567" in values
    assert "+358401234567" in values
    assert any(v.replace(" ", "").startswith("09") for v in values)


def test_recognizer_entity_type():
    rec = FiPhoneRecognizer()
    text = "Puh. +358 50 987 6543"
    results = rec.analyze(text, entities=["PHONE_NUMBER"])
    assert len(results) == 1
    assert results[0].entity_type == "PHONE_NUMBER"
    assert text[results[0].start : results[0].end] == "+358 50 987 6543"


def test_end_to_end_placeholder():
    text = (
        "Yhteyshenkilö Maija, sähköposti a@b.fi, puh. +358 50 987 6543 "
        "tai 040 123 4567."
    )
    results = FiPhoneRecognizer().analyze(text, entities=["PHONE_NUMBER"])
    out, emap, _ = apply_stable_placeholders(text, results)
    assert "+358 50 987 6543" not in out
    assert "040 123 4567" not in out
    assert "[PHONE_1]" in out
    assert "[PHONE_2]" in out or out.count("[PHONE_") >= 1


def test_parenthetical_area_and_mobile():
    """Common FI print forms: (040) 123 4567, (09) 1234 567."""
    samples = [
        "(040) 123 4567",
        "(050) 987 6543",
        "(09) 1234 567",
        "(040)1234567",
        "Puh. (09) 478 4450",
    ]
    for s in samples:
        hits = find_fi_phones(s)
        assert hits, f"missed parenthetical phone in {s!r}"
        # Full number (with parens) should be captured, not only digits after
        joined = " ".join(h[2] for h in hits)
        assert "040" in joined.replace(" ", "") or "050" in joined.replace(
            " ", ""
        ) or "09" in joined.replace(" ", "") or "478" in joined


def test_parenthetical_phone_engine_redacts():
    """Shipped DocumentAnonymizer path redacts (040) … national forms."""
    from anonymizer.anonymize.config import AnonymizerConfig
    from anonymizer.anonymize.engine import DocumentAnonymizer

    text = (
        "Yhteys: (040) 123 4567 tai (09) 1234 567. "
        "Vanha muoto 040 123 4567 edelleen toimii."
    )
    cfg = AnonymizerConfig(mode="strict", lang="fi", use_llm=False)
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    out = r.anonymized_text
    assert "(040) 123 4567" not in out
    assert "(09) 1234 567" not in out
    assert "040 123 4567" not in out
    assert "[PHONE_" in out
    # Original surfaces in reverse map
    originals = set(r.mapping.values())
    assert any("040" in v and "123" in v for v in originals)


def test_unlabeled_international_phones_redacted_at_default_threshold():
    """Presidio scores unlabeled +1/+44 phones ~0.4; default threshold is 0.5.

    Without a phone floor these numbers leak in clear text.
    """
    from anonymizer.anonymize.config import AnonymizerConfig
    from anonymizer.anonymize.engine import DocumentAnonymizer

    text = (
        "Call +1 (415) 555-0199 today or reach the London desk at "
        "+44 20 7946 0958 for support."
    )
    cfg = AnonymizerConfig(mode="strict", lang="en", use_llm=False)
    cfg.apply_mode()
    # Explicit default — the bug is specific to threshold 0.5
    assert cfg.score_threshold == 0.5
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="en")
    out = r.anonymized_text
    assert "+1 (415) 555-0199" not in out, out
    assert "+44 20 7946 0958" not in out, out
    assert "[PHONE_" in out
    originals = set(r.mapping.values())
    assert "+1 (415) 555-0199" in originals
    assert "+44 20 7946 0958" in originals


def test_y_tunnus_not_kept_as_low_confidence_phone():
    """Presidio often tags Y-tunnus as PHONE at 0.4 — must not promote it."""
    from anonymizer.anonymize.config import AnonymizerConfig
    from anonymizer.anonymize.engine import (
        DocumentAnonymizer,
        _is_y_tunnus_like_phone_fp,
        _looks_like_international_phone,
    )

    assert _is_y_tunnus_like_phone_fp("0737546-2")
    assert not _looks_like_international_phone("0737546-2")
    assert not _looks_like_international_phone("1640")
    assert not _looks_like_international_phone("2025-01-01-11")
    assert _looks_like_international_phone("+1 (415) 555-0199")

    # standard mode does not redact FI_BUSINESS_ID — Y-tunnus must stay clear
    # (not promoted to PHONE via the low-confidence floor)
    text = "Y-tunnus 0737546-2 on julkinen tunniste."
    cfg = AnonymizerConfig(mode="standard", lang="fi", use_llm=False)
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    assert "0737546-2" in r.anonymized_text
    assert not any("0737546-2" in v for v in r.mapping.values())
