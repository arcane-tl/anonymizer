"""PDF soft-wrap reflow and email artifact repair."""

from __future__ import annotations

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import DocumentAnonymizer
from anonymizer.extract.pdf import _join_pdf_lines
from anonymizer.extract.text_repair import is_real_web_url, repair_text_artifacts


def test_join_keeps_form_label_newline():
    lines = ["Osoite:", "Testikatu 99 B 2"]
    assert _join_pdf_lines(lines) == "Osoite:\nTestikatu 99 B 2"


def test_join_reflows_body_soft_wrap():
    lines = ["Ajoneuvon vuokraus on sallittu yhteistyössä myyjän", "kanssa, Ajoneuvo on"]
    out = _join_pdf_lines(lines)
    assert "\n" not in out
    assert "myyjän kanssa" in out


def test_join_dehyphenates_soft_hyphen():
    lines = ["ulkomailla sallittu (ETA-", "maat) green card"]
    out = _join_pdf_lines(lines)
    assert "ETA-maat" in out
    assert "ETA-\n" not in out


def test_join_section_header_kept():
    lines = ["MYYJÄLIIKE", "Nimi:", "ACME OY"]
    out = _join_pdf_lines(lines)
    assert "MYYJÄLIIKE\nNimi:\nACME OY" == out


def test_repair_broken_email_tld():
    broken = "Sähköpostiosoite:\nuser.name@example.f\ni"
    fixed = repair_text_artifacts(broken)
    assert "user.name@example.fi" in fixed
    assert "example.f\ni" not in fixed


def test_is_real_web_url():
    assert is_real_web_url("https://example.com/x")
    assert is_real_web_url("www.example.fi")
    assert not is_real_web_url("christofer.sj")
    assert not is_real_web_url("bestcaravan.fi")


def test_split_email_fully_redacted_not_partial_url():
    """PDF-style split must become one EMAIL, never christofer.sj as URL."""
    text = "Sähköpostiosoite:\nada.lovelace@example.f\ni"
    cfg = AnonymizerConfig(mode="strict", lang="en")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="en")
    out = r.anonymized_text
    assert "ada.lovelace@example.fi" not in out
    assert "lovelace@" not in out
    assert "example.f" not in out or "[EMAIL" in out
    # No partial leftover local-part after a URL placeholder
    assert not any(
        v.endswith(".sj") or (len(v) < 20 and "." in v and "@" not in v and "http" not in v)
        for k, v in r.mapping.items()
        if k.startswith("[URL_")
    )
    assert any(k.startswith("[EMAIL_") for k in r.mapping), r.mapping


def test_unbroken_email_still_redacted():
    text = "Contact: ada.lovelace@example.com today."
    cfg = AnonymizerConfig(mode="strict", lang="en")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="en")
    assert "ada.lovelace@example.com" not in r.anonymized_text
    assert "[EMAIL_" in r.anonymized_text
