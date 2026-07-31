"""Vehicle VIN (valmistenumero) recognition — strict mode."""

from __future__ import annotations

from anonymizer.anonymize.config import AnonymizerConfig, STANDARD_ENTITIES, STRICT_ENTITIES
from anonymizer.anonymize.engine import DocumentAnonymizer
from anonymizer.anonymize.recognizers.vin import find_vins


# Synthetic VIN-shaped strings for tests (not real vehicles)
_SAMPLE_VIN = "VF7YGCPAU12W11969"


def test_find_vin_basic():
    text = f"Valmistenumero:\n{_SAMPLE_VIN}"
    hits = find_vins(text)
    assert any(h[2] == _SAMPLE_VIN for h in hits), hits


def test_vin_redacted_in_strict():
    text = f"Valmistenumero:\n{_SAMPLE_VIN}\nRekisterinumero: ABC-123"
    cfg = AnonymizerConfig(mode="strict", lang="fi")
    cfg.apply_mode()
    assert "VEHICLE_VIN" in cfg.effective_entities()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    assert _SAMPLE_VIN not in r.anonymized_text
    assert "[VIN_" in r.anonymized_text
    assert "ABC-123" not in r.anonymized_text  # plate still redacted


def test_vin_not_in_standard_entities():
    assert "VEHICLE_VIN" not in STANDARD_ENTITIES
    assert "VEHICLE_VIN" in STRICT_ENTITIES
    text = f"Valmistenumero: {_SAMPLE_VIN}"
    cfg = AnonymizerConfig(mode="standard", lang="fi")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    assert _SAMPLE_VIN in r.anonymized_text


def test_vin_rejects_all_digits():
    assert find_vins("ID 12345678901234567 serial") == []
