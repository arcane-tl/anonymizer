"""Domain false-positive filters, lexicon, and allowlist_extra."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from anonymizer.anonymize.config import DEFAULT_ALLOWLIST, AnonymizerConfig, load_config
from anonymizer.anonymize.domain_lexicon import (
    is_contract_role_surface,
    is_legal_phrase_surface,
    is_weak_org_stem,
    tokens_all_domain_noise,
)
from anonymizer.anonymize.engine import DocumentAnonymizer, _filter_entity_false_positives
from anonymizer.anonymize.org_stems import company_stems_from_org_surface
from presidio_analyzer import RecognizerResult


def test_lexicon_roles_and_phrases() -> None:
    assert is_contract_role_surface("Asiakas")
    assert is_contract_role_surface("CLIENT")
    assert is_legal_phrase_surface("Force Majeure")
    assert is_weak_org_stem("Nordic")
    assert is_weak_org_stem("Best")
    assert not is_weak_org_stem("LähiTapiola")


def test_tokens_all_domain_noise() -> None:
    assert tokens_all_domain_noise(["Force", "Majeure"]) is False  # phrase handled elsewhere
    assert tokens_all_domain_noise(["Initial", "Delivery", "Date"]) is True
    assert tokens_all_domain_noise(["Alice", "Wonderland"]) is False


def test_stem_rejects_weak_first_token() -> None:
    # Legal form present but first token is generic
    stems = company_stems_from_org_surface("Nordic Widgets Oy")
    assert "Nordic Widgets" in stems or any("Widgets" in s for s in stems)
    assert "Nordic" not in stems


def test_post_merge_drops_role_and_legal_org() -> None:
    text = "Asiakas allekirjoittaa. Force Majeure applies. ACME Oy is real."
    results = [
        RecognizerResult(entity_type="ORG", start=0, end=7, score=0.9),  # Asiakas
        RecognizerResult(
            entity_type="ORG",
            start=text.index("Force Majeure"),
            end=text.index("Force Majeure") + len("Force Majeure"),
            score=0.9,
        ),
        RecognizerResult(
            entity_type="ORG",
            start=text.index("ACME Oy"),
            end=text.index("ACME Oy") + len("ACME Oy"),
            score=0.9,
        ),
    ]
    kept = _filter_entity_false_positives(text, results)
    surfaces = [text[r.start : r.end] for r in kept]
    assert "Asiakas" not in surfaces
    assert "Force Majeure" not in surfaces
    assert "ACME Oy" in surfaces


def test_post_merge_drops_noise_person() -> None:
    text = "Contact Initial Delivery Date then Alice Wonderland."
    idd = "Initial Delivery Date"
    alice = "Alice Wonderland"
    results = [
        RecognizerResult(
            entity_type="PERSON",
            start=text.index(idd),
            end=text.index(idd) + len(idd),
            score=0.9,
        ),
        RecognizerResult(
            entity_type="PERSON",
            start=text.index(alice),
            end=text.index(alice) + len(alice),
            score=0.9,
        ),
    ]
    kept = _filter_entity_false_positives(text, results)
    surfaces = [text[r.start : r.end] for r in kept]
    assert idd not in surfaces
    assert alice in surfaces


def test_default_allowlist_includes_roles() -> None:
    assert "Asiakas" in DEFAULT_ALLOWLIST
    assert "Force Majeure" in DEFAULT_ALLOWLIST
    assert "Y-tunnus" in DEFAULT_ALLOWLIST


def test_allowlist_extra_appends(tmp_path: Path) -> None:
    p = tmp_path / "cfg.yaml"
    p.write_text(
        yaml.safe_dump({"allowlist_extra": ["MyProductX", "Y-tunnus"]}),
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert "MyProductX" in cfg.allowlist
    assert "Y-tunnus" in cfg.allowlist  # default retained
    assert cfg.allowlist.count("Y-tunnus") == 1  # no dup from extra


def test_engine_keeps_asiakas_clear() -> None:
    text = "Asiakas on velvollinen vakuuttamaan leasingkohteen."
    r = DocumentAnonymizer(AnonymizerConfig()).anonymize_text(text, lang_flag="fi")
    assert "Asiakas" in r.anonymized_text
    assert not any(v == "Asiakas" for v in r.mapping.values())
