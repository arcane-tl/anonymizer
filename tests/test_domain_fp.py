"""Domain false-positive filters, lexicon, and allowlist_extra / lexicon_extra."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from anonymizer.anonymize.config import DEFAULT_ALLOWLIST, AnonymizerConfig, load_config
from anonymizer.anonymize.domain_lexicon import (
    builtin_lexicon,
    is_contract_role_surface,
    is_legal_phrase_surface,
    is_role_or_legal_surface,
    is_weak_org_stem,
    merge_lexicon_extra,
    tokens_all_domain_noise,
)
from anonymizer.anonymize.engine import DocumentAnonymizer, _filter_entity_false_positives
from anonymizer.anonymize.org_stems import company_stems_from_org_surface
from presidio_analyzer import RecognizerResult


def test_lexicon_roles_and_phrases() -> None:
    assert is_contract_role_surface("Asiakas")
    assert is_contract_role_surface("CLIENT")
    assert is_contract_role_surface("Vakuutuksenottaja")
    assert is_contract_role_surface("policyholder")
    assert is_contract_role_surface("Yhteyshenkilö")
    assert is_legal_phrase_surface("Force Majeure")
    assert is_legal_phrase_surface("Governing Law")
    assert is_legal_phrase_surface("Sovellettava laki")
    assert is_legal_phrase_surface("Vastuunrajoitus")
    assert is_role_or_legal_surface("insurer")
    assert is_weak_org_stem("Nordic")
    assert is_weak_org_stem("Best")
    assert is_weak_org_stem("omavastuu")
    assert not is_weak_org_stem("LähiTapiola")


def test_tokens_all_domain_noise() -> None:
    assert tokens_all_domain_noise(["Force", "Majeure"]) is False  # phrase handled elsewhere
    assert tokens_all_domain_noise(["Initial", "Delivery", "Date"]) is True
    assert tokens_all_domain_noise(["Limitation", "of", "Liability"]) is True
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


def test_post_merge_drops_new_fi_en_roles() -> None:
    """≥15 new role/phrase surfaces must not stick as ORG/PERSON."""
    samples = [
        ("Vakuutuksenottaja", "ORG"),
        ("Vakuutuksenantaja", "ORG"),
        ("Policyholder", "PERSON"),
        ("Insurer", "ORG"),
        ("Yhteyshenkilö", "PERSON"),
        ("Subcontractor", "ORG"),
        ("Governing Law", "ORG"),
        ("Sovellettava laki", "ORG"),
        ("Vastuunrajoitus", "ORG"),
        ("Salassapito", "ORG"),
        ("Confidential Information", "ORG"),
        ("Limitation of Liability", "ORG"),
        ("Yleiset sopimusehdot", "ORG"),
        ("Lessor", "PERSON"),
        ("Lessee", "ORG"),
        ("Broker", "PERSON"),
        ("Guarantor", "ORG"),
    ]
    assert len(samples) >= 15
    for surface, etype in samples:
        text = f"See {surface} in clause 3. ACME Oy remains."
        start = text.index(surface)
        results = [
            RecognizerResult(
                entity_type=etype, start=start, end=start + len(surface), score=0.9
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
        assert surface not in surfaces, f"FP not dropped: {surface!r}"
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


def test_post_merge_boilerplate_neighbourhood() -> None:
    """ORG noise next to § / clause cues drops; legal-form company kept."""
    text = "§ 4 Definitions applies. Then ACME Logistics Oy signs."
    noise = "Definitions"
    company = "ACME Logistics Oy"
    results = [
        RecognizerResult(
            entity_type="ORG",
            start=text.index(noise),
            end=text.index(noise) + len(noise),
            score=0.9,
        ),
        RecognizerResult(
            entity_type="ORG",
            start=text.index(company),
            end=text.index(company) + len(company),
            score=0.9,
        ),
    ]
    kept = _filter_entity_false_positives(text, results)
    surfaces = [text[r.start : r.end] for r in kept]
    assert noise not in surfaces
    assert company in surfaces


def test_post_merge_drops_commercial_loc_compound() -> None:
    text = "Ylikilometriveloitus is a fee field, not a place. Helsinki is a city."
    fee = "Ylikilometriveloitus"
    city = "Helsinki"
    results = [
        RecognizerResult(
            entity_type="LOCATION",
            start=text.index(fee),
            end=text.index(fee) + len(fee),
            score=0.9,
        ),
        RecognizerResult(
            entity_type="LOCATION",
            start=text.index(city),
            end=text.index(city) + len(city),
            score=0.9,
        ),
    ]
    kept = _filter_entity_false_positives(text, results)
    surfaces = [text[r.start : r.end] for r in kept]
    assert fee not in surfaces
    assert city in surfaces


def test_default_allowlist_includes_roles() -> None:
    assert "Asiakas" in DEFAULT_ALLOWLIST
    assert "Force Majeure" in DEFAULT_ALLOWLIST
    assert "Y-tunnus" in DEFAULT_ALLOWLIST
    assert "Vakuutuksenottaja" in DEFAULT_ALLOWLIST
    assert "Governing Law" in DEFAULT_ALLOWLIST


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


def test_lexicon_extra_merges(tmp_path: Path) -> None:
    p = tmp_path / "cfg.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "lexicon_extra": {
                    "roles": ["CustomRoleX"],
                    "legal_phrases": ["custom legal phrase x"],
                    "allowlist_seeds": ["CustomSeedY"],
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert is_contract_role_surface("CustomRoleX", cfg.lexicon)
    assert is_legal_phrase_surface("Custom Legal Phrase X", cfg.lexicon)
    # Built-ins still present
    assert is_contract_role_surface("Asiakas", cfg.lexicon)
    assert "CustomSeedY" in cfg.allowlist


def test_merge_lexicon_extra_empty_equals_builtin() -> None:
    assert merge_lexicon_extra(None).roles == builtin_lexicon().roles
    assert merge_lexicon_extra({}).roles == builtin_lexicon().roles


def test_engine_keeps_asiakas_clear() -> None:
    text = "Asiakas on velvollinen vakuuttamaan leasingkohteen."
    r = DocumentAnonymizer(AnonymizerConfig()).anonymize_text(text, lang_flag="fi")
    assert "Asiakas" in r.anonymized_text
    assert not any(v == "Asiakas" for v in r.mapping.values())


def test_engine_keeps_vakuutuksenottaja_and_governing_law() -> None:
    fi = "Vakuutuksenottaja maksaa vakuutusmaksun ajallaan."
    en = "Governing Law of this Agreement is Finland. ACME Oy remains."
    r_fi = DocumentAnonymizer(AnonymizerConfig()).anonymize_text(fi, lang_flag="fi")
    r_en = DocumentAnonymizer(AnonymizerConfig()).anonymize_text(en, lang_flag="en")
    assert "Vakuutuksenottaja" in r_fi.anonymized_text
    assert not any(v == "Vakuutuksenottaja" for v in r_fi.mapping.values())
    assert "Governing Law" in r_en.anonymized_text or "governing law" in r_en.anonymized_text.casefold()
    # Synthetic company with legal form still redacted
    assert "ACME Oy" not in r_en.anonymized_text


def test_engine_still_redacts_person_and_company() -> None:
    text = "Alice Wonderland works at Nordic Widgets Oy in Helsinki."
    r = DocumentAnonymizer(AnonymizerConfig()).anonymize_text(text, lang_flag="en")
    assert "Alice Wonderland" not in r.anonymized_text
    assert "Nordic Widgets Oy" not in r.anonymized_text
    assert any("PERSON" in ph for ph in r.mapping)
    assert any("ORG" in ph or "COMPANY" in ph for ph in r.mapping) or any(
        "Widgets" in v or "Nordic" in v for v in r.mapping.values()
    )
