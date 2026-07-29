"""Language detection and --lang resolution."""

from anonymizer.anonymize.language import (
    count_alpha_tokens,
    resolve_language,
    sample_text_for_detection,
    tesseract_lang_string,
)


EN_SAMPLE = """
The quarterly report was prepared by the finance department in London.
Several suppliers delivered equipment under the framework agreement.
The contract terms were reviewed by legal counsel before signing.
Additional appendices describe payment schedules and delivery milestones.
"""

FI_SAMPLE = """
Neljännesvuosiraportin on laatinut talousosasto Helsingissä.
Useat toimittajat toimittivat laitteita puitesopimuksen mukaisesti.
Sopimusehdot tarkisti lakiosasto ennen allekirjoitusta.
Liitteissä kuvataan maksuaikataulut ja toimitusten välitavoitteet.
"""


def test_short_text_defaults_to_mixed():
    d = resolve_language("auto", "Hi")
    assert d.mode == "auto"
    assert set(d.nlp_passes) == {"en", "fi"}
    assert d.reason == "short_text"


def test_forced_en():
    d = resolve_language("en", FI_SAMPLE)
    assert d.mode == "forced"
    assert d.nlp_passes == ["en"]


def test_forced_dual():
    d = resolve_language("en,fi", "x")
    assert d.nlp_passes == ["en", "fi"]


def test_invalid_lang_raises():
    try:
        resolve_language("de", "hello")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_tesseract_langs():
    assert tesseract_lang_string("auto") == "eng+fin"
    assert tesseract_lang_string("en") == "eng"
    assert tesseract_lang_string("fi") == "fin"


def test_sample_long_text():
    long = "a" * 50_000
    s = sample_text_for_detection(long)
    assert len(s) <= 12_000 + 10


def test_count_tokens():
    assert count_alpha_tokens("Hello world 123") == 2


def test_detect_english():
    d = resolve_language("auto", EN_SAMPLE * 2)
    assert d.mode == "auto"
    # Should prefer English-only pass when confident
    assert "en" in d.nlp_passes
    if d.reason.startswith("confident") or d.reason.startswith("weak"):
        assert d.nlp_passes == ["en"]


def test_detect_finnish():
    d = resolve_language("auto", FI_SAMPLE * 2)
    assert d.mode == "auto"
    assert "fi" in d.nlp_passes
    if d.reason.startswith("confident") or d.reason.startswith("weak"):
        assert d.nlp_passes == ["fi"]
