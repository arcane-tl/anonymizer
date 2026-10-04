"""Debug provenance log + source chips."""

from __future__ import annotations

from pathlib import Path

from anonymizer.anonymize.debug_log import (
    build_run_debug_payload,
    format_sources_chip,
    write_run_debug_log,
)
from anonymizer.anonymize.review import ReviewFinding, ReviewSession
from anonymizer.gui.review_window import format_finding_secondary
from anonymizer.models import AnonymizeResult, LanguageDecision


def test_format_sources_chip():
    assert format_sources_chip(["spacy:fi", "pattern:CompanyRecognizer"]) == "spaCy · pattern"
    assert format_sources_chip([]) == ""
    assert format_sources_chip(["denylist", "org_stem"]) == "deny · stem"


def test_write_run_debug_log(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANONYMIZER_DEBUG_LOG", str(tmp_path))
    result = AnonymizeResult(
        anonymized_text="x",
        entity_counts={"PERSON": 1},
        mapping={"[PERSON_1]": "Ada Lovelace"},
        language=LanguageDecision(
            mode="forced", detected=["en"], nlp_passes=["en"], reason="test"
        ),
        hits=[],
        mode="strict",
        proposals={"[ORG_1]": "Soft Org"},
        hit_meta={
            "[PERSON_1]": {
                "entity_type": "PERSON",
                "sources": ["spacy:en"],
            },
            "[ORG_1]": {
                "entity_type": "ORG",
                "sources": ["spacy:en"],
            },
        },
    )
    path = write_run_debug_log(result, source_file="demo.txt", version="test")
    assert path is not None
    assert path.is_file()
    payload = build_run_debug_payload(result, source_file="demo.txt", version="test")
    assert payload["summary"]["auto_redactions"] == 1
    assert payload["summary"]["proposals"] == 1
    assert payload["summary"]["by_source_family"]["spacy"] == 1
    assert any(f["surface"] == "Ada Lovelace" for f in payload["findings"])


def test_review_secondary_shows_chip_when_sources_present():
    f = ReviewFinding(
        placeholder="[PERSON_1]",
        original="Ada",
        entity_type="PERSON",
        detector_sources=["spacy:en"],
    )
    secondary = format_finding_secondary(f)
    assert "spaCy" in secondary


def test_from_mapping_show_sources():
    session = ReviewSession.from_mapping(
        ["Ada works."],
        {"[PERSON_1]": "Ada"},
        hit_meta={"[PERSON_1]": {"sources": ["spacy:en"]}},
        show_sources=True,
    )
    assert session.get("[PERSON_1]").detector_sources == ["spacy:en"]
    session2 = ReviewSession.from_mapping(
        ["Ada works."],
        {"[PERSON_1]": "Ada"},
        hit_meta={"[PERSON_1]": {"sources": ["spacy:en"]}},
        show_sources=False,
    )
    assert session2.get("[PERSON_1]").detector_sources == []
