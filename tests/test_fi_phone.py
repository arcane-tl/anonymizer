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
