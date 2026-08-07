"""Redact style config + CLI surface."""

from __future__ import annotations

from pathlib import Path

import pytest

from anonymizer.anonymize.config import (
    AnonymizerConfig,
    load_config,
    normalize_redact_style,
)


def test_normalize_redact_style_aliases() -> None:
    assert normalize_redact_style(None) == "placeholder"
    assert normalize_redact_style("placeholder") == "placeholder"
    assert normalize_redact_style("tags") == "placeholder"
    assert normalize_redact_style("remove") == "remove"
    assert normalize_redact_style("delete") == "remove"
    with pytest.raises(ValueError):
        normalize_redact_style("blackbox")


def test_load_config_redact_style(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text("redact_style: remove\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.redact_style == "remove"


def test_default_config_placeholder() -> None:
    cfg = AnonymizerConfig()
    assert cfg.redact_style == "placeholder"
