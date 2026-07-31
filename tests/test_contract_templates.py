"""Regression tests against EN/FI contract text templates."""

from __future__ import annotations

from pathlib import Path

import pytest

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import DocumentAnonymizer
from anonymizer.extract.text import extract_text_file
from anonymizer.output.markdown import render_from_extracted

from contract_expected_pii import EN_MUST_REDACT, FI_MUST_REDACT

FIXTURES = Path(__file__).parent / "fixtures"


def _anonymize_file(path: Path, lang: str) -> str:
    doc = extract_text_file(path)
    assert doc.blocks, f"no text extracted from {path}"
    anon = DocumentAnonymizer(AnonymizerConfig(lang=lang))
    texts = [b.text for b in doc.blocks]
    anon_blocks, result = anon.anonymize_blocks(texts, lang_flag=lang)
    md = render_from_extracted(doc, anon_blocks, result)
    return md


@pytest.mark.parametrize(
    "filename,lang,must_redact",
    [
        ("contract_en.txt", "en", EN_MUST_REDACT),
        ("contract_fi.txt", "fi", FI_MUST_REDACT),
        ("contract_fi.txt", "en,fi", FI_MUST_REDACT),
    ],
)
def test_contract_template_redacts_ground_truth(
    filename: str, lang: str, must_redact: list[str]
) -> None:
    path = FIXTURES / filename
    assert path.is_file(), path
    out = _anonymize_file(path, lang)
    # Body should still look like a contract / contain structure
    assert "Agreement" in out or "Sopimus" in out or "sopimus" in out.lower() or "#" in out
    leaks = [s for s in must_redact if s in out]
    assert leaks == [], f"PII still present in {filename} (lang={lang}): {leaks}\n---\n{out}"


def test_contract_templates_exist_and_document_use_cases() -> None:
    en = (FIXTURES / "contract_en.txt").read_text(encoding="utf-8")
    fi = (FIXTURES / "contract_fi.txt").read_text(encoding="utf-8")
    # Smoke: templates mention key categories so they stay comprehensive
    for needle in ("IBAN", "Email", "Phone", "http", "OY", "Street"):
        assert needle.lower() in en.lower() or needle in en
    for needle in ("Y-tunnus", "henkilötunnus", "Mannerheimintie", "+358", "00100", "02330"):
        assert needle.lower() in fi.lower() or needle in fi
