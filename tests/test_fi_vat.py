"""Finnish ALV / VAT number tests."""

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import DocumentAnonymizer, apply_stable_placeholders
from anonymizer.anonymize.recognizers.fi_vat import (
    FiVatRecognizer,
    find_fi_vats,
    is_valid_fi_vat,
)


def test_valid_checksum():
    assert is_valid_fi_vat("07375462")  # from Y-tunnus 0737546-2
    assert is_valid_fi_vat("28567738")  # FI28567738 shape


def test_invalid_checksum_rejected():
    assert not is_valid_fi_vat("07375461")
    assert not is_valid_fi_vat("12345678")


def test_find_formats():
    text = "ALV-numero: FI07375462 and FI 07375462 and FI-07375462."
    hits = find_fi_vats(text)
    assert len(hits) >= 1
    assert all("07375462" in h[2].replace(" ", "").replace("-", "").upper() for h in hits)


def test_user_example_format():
    text = "ALV-numero: FI28567738"
    results = FiVatRecognizer().analyze(text, entities=["FI_VAT"])
    assert len(results) == 1
    out, _, _ = apply_stable_placeholders(text, results)
    assert "FI28567738" not in out
    assert "[VAT_FI_1]" in out


def test_end_to_end_alv_line():
    text = "ALV-numero: FI28567738\nY-tunnus: 0737546-2"
    r = DocumentAnonymizer(AnonymizerConfig(lang="fi")).anonymize_text(
        text, lang_flag="fi"
    )
    assert "FI28567738" not in r.anonymized_text
    assert "0737546-2" not in r.anonymized_text
    assert "[VAT_FI_" in r.anonymized_text
    assert "FI_BUSINESS_ID" in r.entity_counts or "[FI_BUSINESS_ID_" in r.anonymized_text
