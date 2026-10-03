"""Unit tests for Apple FM AI check (mocked — no model required)."""

from __future__ import annotations

from anonymizer.anonymize.ai_check import (
    AUTO_DROP_TYPES,
    AiCheckResult,
    FindingVerdict,
    MissProposal,
    apply_ai_check_to_session,
    build_ai_check_prompt,
    parse_ai_check_response,
    run_ai_check,
)
from anonymizer.anonymize.review import ReviewSession


def test_parse_ai_check_response_basic():
    raw = """
    {
      "verdicts": [
        {"id": "[ORG_1]", "decision": "drop", "confidence": "high", "reason": "boilerplate"},
        {"id": "[PERSON_1]", "decision": "keep", "confidence": "high", "reason": "name"}
      ],
      "misses": [
        {"type": "EMAIL_ADDRESS", "text": "a@b.test", "confidence": "high", "reason": "missed"}
      ]
    }
    """
    verdicts, misses = parse_ai_check_response(
        raw, valid_placeholders={"[ORG_1]", "[PERSON_1]"}
    )
    assert len(verdicts) == 2
    assert verdicts[0].decision == "drop"
    assert verdicts[1].decision == "keep"
    assert len(misses) == 1
    assert misses[0].entity_type == "EMAIL_ADDRESS"


def test_parse_ignores_unknown_placeholders():
    raw = '{"verdicts":[{"id":"[ORG_99]","decision":"drop"}],"misses":[]}'
    verdicts, misses = parse_ai_check_response(
        raw, valid_placeholders={"[ORG_1]"}
    )
    assert verdicts == []
    assert misses == []


def test_build_prompt_includes_findings():
    prompt = build_ai_check_prompt(
        findings=[{"id": "[ORG_1]", "type": "ORG", "text": "Acme", "context": "…"}],
        miss_chunks=["Contact ada@example.test"],
        entity_types=["ORG", "EMAIL_ADDRESS"],
    )
    assert "[ORG_1]" in prompt
    assert "ada@example.test" in prompt
    assert "EMAIL_ADDRESS" in prompt


def test_apply_auto_only_high_confidence_soft_types():
    blocks = ["Force Majeure and Acme Oy. Email bob@example.com"]
    mapping = {
        "[ORG_1]": "Force Majeure",
        "[ORG_2]": "Acme Oy",
        "[EMAIL_1]": "bob@example.com",
    }
    session = ReviewSession.from_mapping(blocks, mapping)
    result = AiCheckResult(
        ran=True,
        provider="apple",
        verdicts=[
            FindingVerdict("[ORG_1]", "drop", "boilerplate", "high"),
            FindingVerdict("[ORG_2]", "drop", "maybe", "medium"),  # not high
            FindingVerdict("[EMAIL_1]", "drop", "no", "high"),  # not soft type
        ],
        misses=[
            MissProposal("EMAIL_ADDRESS", "bob@example.com", "dup", "high"),
        ],
    )
    stats = apply_ai_check_to_session(session, result, auto_apply=True)
    assert stats["drops"] == 1
    assert session.get("[ORG_1]") and not session.get("[ORG_1]").enabled
    assert session.get("[ORG_2]") and session.get("[ORG_2]").enabled
    assert session.get("[EMAIL_1]") and session.get("[EMAIL_1]").enabled
    assert "ORG" in AUTO_DROP_TYPES


def test_apply_review_mode_pre_unchecks_all_drops_and_adds_misses():
    blocks = ["Alice and secret@example.com met."]
    mapping = {"[PERSON_1]": "Alice"}
    session = ReviewSession.from_mapping(blocks, mapping)
    result = AiCheckResult(
        ran=True,
        provider="apple",
        verdicts=[FindingVerdict("[PERSON_1]", "drop", "role?", "medium")],
        misses=[
            MissProposal("EMAIL_ADDRESS", "secret@example.com", "missed", "high"),
        ],
    )
    stats = apply_ai_check_to_session(session, result, auto_apply=False)
    assert stats["drops"] == 1
    assert not session.get("[PERSON_1]").enabled
    assert stats["misses"] == 1
    assert any(f.original == "secret@example.com" for f in session.findings)


def test_run_ai_check_disabled():
    r = run_ai_check(
        original_blocks=["x"],
        mapping={"[ORG_1]": "Acme"},
        enabled=False,
    )
    assert not r.ran
    assert r.skip_reason == "disabled"


def test_run_ai_check_no_mapping():
    r = run_ai_check(original_blocks=["x"], mapping={}, enabled=True)
    assert not r.ran
    assert r.skip_reason == "no findings"
