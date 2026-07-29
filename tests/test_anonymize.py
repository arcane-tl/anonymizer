"""Anonymization tests (pattern-based without requiring spaCy when possible)."""

from anonymizer.anonymize.engine import apply_stable_placeholders
from anonymizer.anonymize.mapping import EntityMap
from anonymizer.anonymize.recognizers.fi_hetu import FiHetuRecognizer
from anonymizer.output.markdown import render_markdown
from anonymizer.models import AnonymizeResult, LanguageDecision, TextBlock, BlockKind
from presidio_analyzer import RecognizerResult


def test_apply_stable_placeholders_order():
    text = "Alice met Alice and Bob."
    results = [
        RecognizerResult(entity_type="PERSON", start=0, end=5, score=0.9),
        RecognizerResult(entity_type="PERSON", start=10, end=15, score=0.9),
        RecognizerResult(entity_type="PERSON", start=20, end=23, score=0.9),
    ]
    out, emap, hits = apply_stable_placeholders(text, results)
    assert out == "[PERSON_1] met [PERSON_1] and [PERSON_2]."
    assert emap.reverse["[PERSON_1]"] == "Alice"
    assert len(hits) == 3


def test_email_like_manual_result():
    text = "Contact jane.doe@example.com today."
    # simulate email span
    start = text.index("jane.doe@example.com")
    end = start + len("jane.doe@example.com")
    results = [
        RecognizerResult(entity_type="EMAIL_ADDRESS", start=start, end=end, score=1.0)
    ]
    out, _, _ = apply_stable_placeholders(text, results)
    assert "jane.doe@example.com" not in out
    assert "[EMAIL_1]" in out


def test_hetu_in_text_via_recognizer():
    text = "Hetu 131052-308T loppu."
    rec = FiHetuRecognizer()
    results = rec.analyze(text, entities=["FI_HETU"])
    out, _, _ = apply_stable_placeholders(text, results)
    assert "131052-308T" not in out
    assert "[FI_HETU_1]" in out


def test_render_markdown_front_matter():
    result = AnonymizeResult(
        anonymized_text="Hello [PERSON_1]",
        entity_counts={"PERSON": 1},
        mapping={"[PERSON_1]": "Alice"},
        language=LanguageDecision(
            mode="auto", detected=["en"], nlp_passes=["en"], reason="test"
        ),
    )
    md = render_markdown(
        "x.txt",
        [TextBlock(text="Hello [PERSON_1]", kind=BlockKind.PARAGRAPH)],
        result,
    )
    assert md.startswith("---\n")
    assert "lang_mode: auto" in md
    assert "Hello [PERSON_1]" in md
