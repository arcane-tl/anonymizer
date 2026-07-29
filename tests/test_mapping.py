"""Tests for stable EntityMap."""

from anonymizer.anonymize.mapping import EntityMap, normalize_entity_text


def test_normalize_collapses_whitespace_and_case():
    assert normalize_entity_text("  Jane   Doe ") == "jane doe"


def test_stable_placeholders_same_person():
    m = EntityMap()
    a = m.get_or_assign("PERSON", "Jane Doe")
    b = m.get_or_assign("PERSON", "jane  doe")
    c = m.get_or_assign("PERSON", "John Smith")
    assert a == "[PERSON_1]"
    assert b == "[PERSON_1]"
    assert c == "[PERSON_2]"
    assert m.reverse["[PERSON_1]"] == "Jane Doe"


def test_different_types_independent_counters():
    m = EntityMap()
    assert m.get_or_assign("PERSON", "Acme") == "[PERSON_1]"
    assert m.get_or_assign("ORG", "Acme") == "[ORG_1]"
    assert m.get_or_assign("EMAIL_ADDRESS", "a@b.com") == "[EMAIL_1]"
