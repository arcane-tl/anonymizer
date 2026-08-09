"""ReviewSession: toggle FPs, add redactions, apply from original blocks."""

from __future__ import annotations

import pytest

from anonymizer.anonymize.review import (
    ReviewFinding,
    ReviewSession,
    apply_mapping_to_blocks,
    count_surface_occurrences,
    entity_type_from_placeholder,
    placeholder_type_label,
    resolve_surface_in_blocks,
)
from anonymizer.gui.review_window import ellipsize_text, format_finding_row


def test_placeholder_type_helpers():
    assert placeholder_type_label("[ORG_1]") == "ORG"
    assert placeholder_type_label("[PLATE_FI_2]") == "PLATE_FI"
    assert entity_type_from_placeholder("[EMAIL_1]") == "EMAIL_ADDRESS"
    assert entity_type_from_placeholder("[PERSON_3]") == "PERSON"


def test_count_and_apply_mapping():
    blocks = ["Hello ACME OY and ACME OY again.", "Phone 0401234567"]
    assert count_surface_occurrences(blocks, "ACME OY") == 2
    mapping = {"[ORG_1]": "ACME OY", "[PHONE_1]": "0401234567"}
    out = apply_mapping_to_blocks(blocks, mapping)
    assert "[ORG_1]" in out[0] and "ACME OY" not in out[0]
    assert out[0].count("[ORG_1]") == 2
    assert "[PHONE_1]" in out[1]


def test_session_toggle_keep_clear():
    blocks = ["Contact ACME OY at 0401234567."]
    mapping = {"[ORG_1]": "ACME OY", "[PHONE_1]": "0401234567"}
    session = ReviewSession.from_mapping(blocks, mapping)
    assert session.summary_counts()["redact"] == 2

    assert session.set_enabled("[ORG_1]", False)
    assert "[ORG_1]" in session.keep_clear_placeholders()
    assert "[ORG_1]" not in session.active_mapping()

    anon, active = session.apply()
    assert "ACME OY" in anon[0]
    assert "[PHONE_1]" in anon[0]
    assert "0401234567" not in anon[0]
    assert active == {"[PHONE_1]": "0401234567"}


def test_session_pre_keep_clear():
    blocks = ["ACME OY only"]
    mapping = {"[ORG_1]": "ACME OY"}
    session = ReviewSession.from_mapping(
        blocks, mapping, pre_keep_clear=["[ORG_1]"]
    )
    assert session.get("[ORG_1]") is not None
    assert session.get("[ORG_1]").enabled is False
    anon, active = session.apply()
    assert anon[0] == "ACME OY only"
    assert active == {}


def test_session_add_redaction():
    blocks = [
        "Service between Nordic Widgets Oy and Partner Co.",
        "Sign: Maija Korhonen",
    ]
    mapping = {"[ORG_1]": "Nordic Widgets Oy"}
    session = ReviewSession.from_mapping(blocks, mapping)

    added = session.add_redaction("Maija Korhonen", "PERSON")
    assert added.source == "user"
    assert added.placeholder == "[PERSON_1]"
    assert added.enabled is True
    assert session.summary_counts()["user_added"] == 1

    anon, active = session.apply()
    assert "[ORG_1]" in anon[0]
    assert "Nordic Widgets Oy" not in anon[0]
    assert "[PERSON_1]" in anon[1]
    assert "Maija Korhonen" not in anon[1]
    assert active["[PERSON_1]"] == "Maija Korhonen"


def test_session_add_same_surface_reenables():
    blocks = ["ACME OY here"]
    mapping = {"[ORG_1]": "ACME OY"}
    session = ReviewSession.from_mapping(blocks, mapping)
    session.set_enabled("[ORG_1]", False)
    again = session.add_redaction("ACME OY", "ORG")
    assert again.placeholder == "[ORG_1]"
    assert again.enabled is True
    assert session.summary_counts()["user_added"] == 0  # still auto


def test_session_add_allocates_next_number():
    blocks = ["Alice and Bob"]
    mapping = {"[PERSON_1]": "Alice"}
    session = ReviewSession.from_mapping(blocks, mapping)
    bob = session.add_redaction("Bob", "PERSON")
    assert bob.placeholder == "[PERSON_2]"


def test_session_apply_remove_style():
    blocks = ["See ACME OY now."]
    mapping = {"[ORG_1]": "ACME OY"}
    session = ReviewSession.from_mapping(blocks, mapping)
    anon, _ = session.apply(style="remove")
    assert "ACME OY" not in anon[0]
    assert "[ORG_1]" not in anon[0]


def test_format_finding_row():
    f = ReviewFinding(
        placeholder="[PERSON_1]",
        original="Tomi Lindroos",
        entity_type="PERSON",
        enabled=True,
        source="auto",
        occurrence_count=1,
    )
    assert format_finding_row(f) == "[x] Tomi Lindroos  (Person · [PERSON_1])"

    f2 = ReviewFinding(
        placeholder="[ORG_1]",
        original="Acme Ltd",
        entity_type="ORG",
        enabled=False,
        source="user",
        occurrence_count=3,
    )
    assert format_finding_row(f2) == "[ ] Acme Ltd ×3  (Organization · [ORG_1] · added)"


def test_ellipsize_text():
    class _FakeFont:
        def measure(self, s: str) -> int:
            return len(s) * 10  # 10px per char

    font = _FakeFont()
    assert ellipsize_text("hello", font, 1000) == "hello"
    out = ellipsize_text("hello world", font, 50)  # 5*10 budget for ellipsis 1 char
    assert out.endswith("…")
    assert font.measure(out) <= 50


def test_resolve_surface_in_blocks():
    blocks = ["Hello Tomi Lindroos here."]
    assert resolve_surface_in_blocks(blocks, "  Tomi Lindroos  ") == "Tomi Lindroos"
    assert resolve_surface_in_blocks(blocks, "not present") is None


def test_add_redaction_rejects_missing_surface():
    session = ReviewSession.from_mapping(["Hello world"], {})
    with pytest.raises(ValueError, match="Could not find"):
        session.add_redaction("Nobody", "PERSON")
