"""Finnish ID recognizer unit tests."""

from anonymizer.anonymize.recognizers.fi_business_id import (
    FiBusinessIdRecognizer,
    is_valid_y_tunnus,
)
from anonymizer.anonymize.recognizers.fi_hetu import FiHetuRecognizer, is_valid_hetu


def test_hetu_checksum_known_valid():
    # Well-known test format: 010101-123N is a classic example used in docs
    # Verify algorithm with a computed valid code
    # date 010101 + individual 123 → n = 010101123 % 31
    # Check char table: 0123456789ABCDEFHJKLMNPRSTUVWXY
    assert is_valid_hetu("010101-123N") or is_valid_hetu("010101A123N")
    # Construct: 131052-308T is commonly cited as valid
    assert is_valid_hetu("131052-308T")


def test_hetu_invalid_checksum():
    assert not is_valid_hetu("131052-308X")
    assert not is_valid_hetu("000000-0000")


def test_hetu_recognizer_finds_valid():
    rec = FiHetuRecognizer()
    rec.load()
    text = "Henkilötunnus: 131052-308T ja muuta."
    results = rec.analyze(text, entities=["FI_HETU"])
    assert len(results) == 1
    assert results[0].entity_type == "FI_HETU"
    assert text[results[0].start : results[0].end] == "131052-308T"


def test_y_tunnus_valid():
    # 0737546-2 is a known valid format example (Nokia historically etc.)
    # Use algorithm: craft valid
    # 1234567 with check: weights 7,9,10,5,8,4,2
    assert is_valid_y_tunnus("0737546", "2")


def test_y_tunnus_invalid():
    assert not is_valid_y_tunnus("1234567", "0")


def test_business_id_recognizer():
    rec = FiBusinessIdRecognizer()
    rec.load()
    text = "Y-tunnus 0737546-2 näkyy sopimuksessa."
    results = rec.analyze(text, entities=["FI_BUSINESS_ID"])
    assert len(results) == 1
    assert text[results[0].start : results[0].end] == "0737546-2"
