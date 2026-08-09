"""Custom YAML recognizers and entity registry integration."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from anonymizer.anonymize.config import AnonymizerConfig, load_config
from anonymizer.anonymize.engine import DocumentAnonymizer
from anonymizer.anonymize.entity_types import builtin_entity_registry
from anonymizer.anonymize.plugins import load_yaml_pattern_recognizer
from anonymizer.anonymize.recognizers.pattern_list import PatternListRecognizer, PatternSpec


def test_pattern_list_recognizer_matches() -> None:
    rec = PatternListRecognizer(
        name="TestEmp",
        entity_type="EMPLOYEE_ID",
        patterns=[PatternSpec(name="a", regex=r"\bEMP-\d{6}\b", score=0.9)],
    )
    text = "Badge EMP-123456 and noise EMP-12."
    hits = rec.analyze(text, entities=["EMPLOYEE_ID"])
    assert len(hits) == 1
    assert text[hits[0].start : hits[0].end] == "EMP-123456"


def test_yaml_plugin_via_config(tmp_path: Path) -> None:
    yaml_path = tmp_path / "emp.yaml"
    yaml_path.write_text(
        """
name: Emp
entity_type: EMPLOYEE_ID
label: EMP_ID
priority: 3
modes: [strict, standard]
patterns:
  - name: badge
    regex: '\\bEMP-\\d{6}\\b'
    score: 0.9
""",
        encoding="utf-8",
    )
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"recognizers": [{"path": "emp.yaml"}]}),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert any(
        getattr(r, "supported_entities", None) == ["EMPLOYEE_ID"]
        for r in cfg.plugin_recognizers
    )
    assert cfg.entity_registry.get("EMPLOYEE_ID") is not None
    assert cfg.entity_registry.label_for("EMPLOYEE_ID") == "EMP_ID"
    # Joins strict preset
    assert "EMPLOYEE_ID" in cfg.entities

    text = "Contact Alice Wonderland. Badge EMP-654321."
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="en")
    assert "EMP-654321" not in r.anonymized_text
    assert any(v == "EMP-654321" for v in r.mapping.values())
    assert any(k.startswith("[EMP_ID_") for k in r.mapping)


def test_builtin_registry_presets_match_history() -> None:
    reg = builtin_entity_registry()
    strict = set(reg.codes_for_mode("strict"))
    # Core historical types
    for code in (
        "PERSON",
        "ORG",
        "EMAIL_ADDRESS",
        "FI_HETU",
        "VEHICLE_VIN",
    ):
        assert code in strict
    standard = set(reg.codes_for_mode("standard"))
    assert "PERSON" in standard
    assert "ORG" not in standard
    assert "FI_HETU" in standard


def test_example_employee_yaml_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    example = root / "examples" / "plugins" / "employee_id.yaml"
    if not example.is_file():
        pytest.skip("example plugin missing")
    rec, spec = load_yaml_pattern_recognizer(example)
    assert spec.code == "EMPLOYEE_ID"
    assert "EMP_ID" == spec.label
    hits = rec.analyze("id EMP-000001 here", entities=["EMPLOYEE_ID"])
    assert len(hits) == 1


def test_invalid_recognizer_path_errors(tmp_path: Path) -> None:
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"recognizers": [{"path": "missing.yaml"}]}),
        encoding="utf-8",
    )
    from anonymizer.anonymize.config import ConfigError

    with pytest.raises(ConfigError, match="Failed to load"):
        load_config(cfg_path)
