"""Single-pass block anonymization: offsets + shared placeholders."""

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import (
    DocumentAnonymizer,
    _block_ranges,
    _project_results_to_block,
)
from presidio_analyzer import RecognizerResult


def test_block_ranges_with_separator():
    blocks = ["aaa", "bb", "c"]
    ranges = _block_ranges(blocks, sep="\n\n")
    joined = "\n\n".join(blocks)
    assert ranges == [(0, 3), (5, 7), (9, 10)]
    for block, (s, e) in zip(blocks, ranges, strict=True):
        assert joined[s:e] == block


def test_project_results_to_block():
    # joined: "Hello Alice\n\nMeet Alice again"
    # Alice at 6-11 and 17-22
    results = [
        RecognizerResult(entity_type="PERSON", start=6, end=11, score=0.9),
        RecognizerResult(entity_type="PERSON", start=17, end=22, score=0.9),
    ]
    b0 = _project_results_to_block(results, 0, 11)
    assert len(b0) == 1
    assert b0[0].start == 6 and b0[0].end == 11
    b1 = _project_results_to_block(results, 13, 28)
    assert len(b1) == 1
    assert b1[0].start == 4 and b1[0].end == 9  # 17-13=4


def test_shared_placeholders_across_blocks():
    blocks = [
        "Contact Alice Example at office.",
        "Alice Example signed the form.",
        "No names here.",
    ]
    anon = DocumentAnonymizer(AnonymizerConfig(lang="en"))
    out_blocks, result = anon.anonymize_blocks(blocks, lang_flag="en")
    # Same person surface → same placeholder id in both blocks
    assert "Alice Example" not in "\n".join(out_blocks)
    # Both blocks should share PERSON_1 if NER/heuristic found the name
    if "[PERSON_1]" in out_blocks[0]:
        assert "[PERSON_1]" in out_blocks[1]
    assert result.language.nlp_passes == ["en"]
