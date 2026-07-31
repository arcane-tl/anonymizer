"""Precision tests on realworld-style documents (false-positive guardrails).

Also verifies that synthetic annex PII is still redacted (recall), and that
redaction map values look like genuine sensitive data rather than legal noise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import DocumentAnonymizer
from anonymizer.extract.text import extract_text_file

REALWORLD = Path(__file__).parent / "fixtures" / "realworld"


def _load_must_not(path: Path) -> list[str]:
    items: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    return items


def _anonymize_offline(path: Path, lang: str):
    doc = extract_text_file(path)
    blocks = [b.text for b in doc.blocks]
    cfg = AnonymizerConfig(lang=lang, use_llm=False)
    out_blocks, result = DocumentAnonymizer(cfg).anonymize_blocks(
        blocks, lang_flag=lang
    )
    return "\n\n".join(out_blocks), result


@pytest.mark.parametrize(
    "doc_name,must_not_name,lang",
    [
        ("en_sample_agreement.txt", "en_sample_agreement.must_not_redact.txt", "en"),
        ("fi_sample_sopimus.txt", "fi_sample_sopimus.must_not_redact.txt", "fi"),
    ],
)
def test_realworld_precision_boilerplate_survives(
    doc_name: str, must_not_name: str, lang: str
) -> None:
    doc_path = REALWORLD / doc_name
    must_path = REALWORLD / must_not_name
    assert doc_path.is_file(), doc_path
    assert must_path.is_file(), must_path

    source = doc_path.read_text(encoding="utf-8")
    must_not = _load_must_not(must_path)
    # Only check tokens that actually appear in the source
    required = [t for t in must_not if t in source]
    assert required, "must_not list has no tokens present in source"

    out, _ = _anonymize_offline(doc_path, lang)
    missing = [t for t in required if t not in out]
    assert missing == [], (
        f"False positives: boilerplate redacted in {doc_name}: {missing}"
    )


def test_fi_realworld_still_redacts_synthetic_pii() -> None:
    """Annex synthetic identifiers must still be removed (recall smoke)."""
    out, _ = _anonymize_offline(REALWORLD / "fi_sample_sopimus.txt", "fi")
    for leak in (
        "NORDIC WIDGETS OY",
        "SILVER PINE",
        "ACME LOGISTICS AB",
        "COPPER LAKE",
        "0737546-2",
        "FI07375462",
        "Maija Korhonen",
        "Pekka Nieminen",
        "maija.korhonen@nordic-widgets.example.fi",
        "pekka.nieminen@acme-logistics.example.fi",
        "+358 50 987 6543",
        "040 123 4567",
        "Mannerheimintie 12",
        "Aleksanterinkatu 1",
        "00100",
        "02330",
        "ABC-123",
        "131052-308T",
        "FI21 1234 5600 0007 85",
    ):
        assert leak not in out, f"missed redaction: {leak}"


def test_en_realworld_still_redacts_synthetic_pii() -> None:
    """EN annex synthetic identifiers must still be removed (recall smoke)."""
    out, _ = _anonymize_offline(REALWORLD / "en_sample_agreement.txt", "en")
    for leak in (
        "NORDIC WIDGETS OY",
        "SILVER PINE",
        "ACME LOGISTICS LTD",
        "Jordan Avery Blake",
        "Morgan Ellis Quinn",
        "jordan.blake@nordic-widgets.example.com",
        "morgan.quinn@acme-logistics.example.com",
        "+1 (415) 555-0199",
        "+44 20 7946 0958",
        "500 Market Street",
        "12 Baker Street",
        "GB29 NWBK 6016 1331 9268 19",
        "203.0.113.42",
        "ABC-123",
        "https://www.nordic-widgets.example.com/services",
    ):
        assert leak not in out, f"missed redaction: {leak}"


# Surfaces that are legal noise / form labels — must never appear in reverse maps.
_MAP_FALSE_POSITIVE_SURFACES = frozenset(
    {
        "lien",
        "Manuscript",
        "Work",
        "PDF",
        "MOU",
        "LOI",
        "Initial Delivery Date",
        "Letter of Intent",
        "Memorandum of Understanding",
        "Permissions",
        "WHEREAS",
        "Copyright",
        "Section",
        "Agreement",
        "Publisher",
        "Author",
        "Sopimus",
        "Y-tunnus",
        "ALV-numero",
        "Osoite",
        "Yhteyshenkilö",
        "Toimittaja",
        "Tilaaja",
        "Rekisterinumero/tunniste",
        "Postinumero ja Toimipaikka",
        "Payment IBAN",
        "European Contract Law",
        "United Nations Convention",
        "England and Wales",
        "UK Contract Law Caselist",
        "Wikipedia FI",
        "University of Maine Publishing Agreement",
        "Maine Publishing Agreement",
    }
)


@pytest.mark.parametrize(
    "doc_name,lang",
    [
        ("en_sample_agreement.txt", "en"),
        ("fi_sample_sopimus.txt", "fi"),
    ],
)
def test_realworld_map_values_are_not_legal_noise(doc_name: str, lang: str) -> None:
    """Every reverse-map surface should look like real PII/location, not boilerplate."""
    _, result = _anonymize_offline(REALWORLD / doc_name, lang)
    bad = []
    for placeholder, original in result.mapping.items():
        surface = original.strip()
        if surface in _MAP_FALSE_POSITIVE_SURFACES:
            bad.append((placeholder, surface))
        if "\n" in surface or "\r" in surface:
            bad.append((placeholder, f"multiline:{surface!r}"))
        # Role word glued onto company (quality of span)
        low = surface.casefold()
        for role in (
            "client ",
            "customer ",
            "toimittaja ",
            "tilaaja ",
            "brändiä ",
            "brand ",
        ):
            if low.startswith(role):
                bad.append((placeholder, f"role_prefix:{surface!r}"))
    assert bad == [], f"suspicious map entries in {doc_name}: {bad}"


def test_map_audit_classifies_en_contract_redactions() -> None:
    """Structured EN contract: map should cover PII types without obvious FPs."""
    path = Path(__file__).parent / "fixtures" / "contract_en.txt"
    _, result = _anonymize_offline(path, "en")
    types_seen = set()
    for ph in result.mapping:
        body = ph.strip("[]")
        parts = body.split("_")
        label = "_".join(parts[:-1]) if parts[-1].isdigit() else body
        types_seen.add(label)

    # Expect structured categories on the dense contract template
    for needed in ("ORG", "EMAIL", "PHONE", "STREET", "URL", "IBAN"):
        assert needed in types_seen, f"missing type {needed} in {types_seen}"

    for ph, original in result.mapping.items():
        assert "\n" not in original
        assert original.strip() not in _MAP_FALSE_POSITIVE_SURFACES
        assert not original.casefold().startswith("client ")
        assert not original.casefold().startswith("toimittaja ")
