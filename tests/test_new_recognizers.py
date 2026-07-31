"""Tests for plate, URL, street, company, postal, and brand recognizers.

Uses arbitrary synthetic names only — no production hard-coded company catalog.
"""

import re

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import DocumentAnonymizer, apply_stable_placeholders
from anonymizer.anonymize.recognizers.brand_org import BrandOrgRecognizer, find_brand_orgs
from anonymizer.anonymize.recognizers.company import CompanyRecognizer, find_companies
from anonymizer.anonymize.recognizers.fi_plate import FiPlateRecognizer, find_fi_plates
from anonymizer.anonymize.recognizers.fi_postal import find_fi_postals
from anonymizer.anonymize.recognizers.street import StreetRecognizer, find_streets
from anonymizer.anonymize.recognizers.url import WebUrlRecognizer, find_urls


def test_plate_generic():
    text = "Rekisterinumero XYZ-987 on vanha."
    hits = find_fi_plates(text)
    assert any(h[2].upper() == "XYZ-987" for h in hits)
    results = FiPlateRecognizer().analyze(text, entities=["FI_LICENSE_PLATE"])
    out, _, _ = apply_stable_placeholders(text, results)
    assert "XYZ-987" not in out
    assert "[PLATE_FI_1]" in out


def test_urls():
    text = "Katso https://example.com/a ja www.example.org sekä http://x.example/path?q=1."
    hits = find_urls(text)
    assert len(hits) >= 3
    results = WebUrlRecognizer().analyze(text, entities=["URL"])
    out, _, _ = apply_stable_placeholders(text, results)
    assert "https://example.com/a" not in out
    assert "www.example.org" not in out
    assert "[URL_" in out


def test_finnish_street_with_number():
    text = "Toimitus: Testikatu 99 B 2, Helsinki."
    hits = find_streets(text)
    assert any("Testikatu" in h[2] for h in hits)
    results = StreetRecognizer().analyze(
        text, entities=["STREET", "CITY", "FI_POSTAL_CODE", "LOCATION"]
    )
    out, _, _ = apply_stable_placeholders(text, results)
    assert "Testikatu 99" not in out
    assert "[STREET_" in out


def test_full_finnish_address_decomposed_tags():
    """Street + number + postcode + city → STREET + POSTAL + CITY."""
    from anonymizer.anonymize.recognizers.street import find_address_hits

    text = "Toimitusosoite: Avainkierto 11, 02330 ESPOO. Kiitos."
    hits = find_address_hits(text)
    types = {h[4] for h in hits}
    assert "STREET" in types
    assert "FI_POSTAL_CODE" in types
    assert "CITY" in types

    r = DocumentAnonymizer(AnonymizerConfig(lang="fi")).anonymize_text(
        text, lang_flag="fi"
    )
    out = r.anonymized_text
    assert "Avainkierto 11" not in out
    assert "02330" not in out
    assert "ESPOO" not in out
    assert "[STREET_" in out
    assert "[POSTAL_" in out
    assert "[CITY_" in out


def test_glued_house_number_and_split_form_address():
    """Form layout: street+17a on one block, postcode+city below."""
    from anonymizer.anonymize.recognizers.street import find_address_hits

    text = (
        "Osoite:\n"
        "Avainkierto 17a\n"
        "\n"
        "Postinumero ja Toimipaikka:\n"
        "02330 ESPOO\n"
    )
    hits = find_address_hits(text)
    assert any(h[4] == "STREET" and "17a" in h[2] for h in hits), hits
    assert any(h[4] == "FI_POSTAL_CODE" and h[2] == "02330" for h in hits), hits
    assert any(h[4] == "CITY" and h[2] == "ESPOO" for h in hits), hits

    r = DocumentAnonymizer(AnonymizerConfig(lang="fi")).anonymize_text(
        text, lang_flag="fi"
    )
    out = r.anonymized_text
    assert "17a" not in out
    assert "02330" not in out
    assert "ESPOO" not in out
    assert "Avainkierto" not in out
    assert "[STREET_" in out
    assert "[POSTAL_" in out
    assert "[CITY_" in out

    blocks = ["Osoite:\nAvainkierto 17a", "Postinumero ja Toimipaikka:\n02330 ESPOO"]
    out_blocks, res = DocumentAnonymizer(AnonymizerConfig(lang="fi")).anonymize_blocks(
        blocks, lang_flag="fi"
    )
    joined = "\n\n".join(out_blocks)
    assert "17a" not in joined
    assert "02330" not in joined
    assert "ESPOO" not in joined
    assert "Avainkierto" not in joined
    assert "Postinumero ja Toimipaikka:" in joined
    assert "[STREET_" in joined
    assert "[POSTAL_" in joined
    assert "[CITY_" in joined


def test_company_legal_forms_case_insensitive():
    """Any name + legal suffix, including ALL CAPS OY / LTD."""
    samples = [
        "NORDIC WIDGETS OY",
        "Nordic Widgets Oy",
        "ACME SUPPLIES LTD",
        "Acme Supplies Ltd",
        "POHJOLAN KULJETUS AB",
        "Alpha Bravo Oyj",
    ]
    for name in samples:
        text = f"Sopimus {name} kanssa."
        hits = find_companies(text)
        assert any(
            name.casefold() in h[2].casefold() for h in hits
        ), f"missed company form: {name!r} in {hits}"


def test_company_all_caps_oy_redacted():
    text = "We ordered from NORDIC WIDGETS OY yesterday."
    results = CompanyRecognizer().analyze(text, entities=["ORG"])
    out, emap, _ = apply_stable_placeholders(text, results)
    assert "NORDIC WIDGETS OY" not in out
    assert "[ORG_1]" in out


def test_brand_multiword_title_and_all_caps():
    """Multi-word names without legal suffix — Title Case and ALL CAPS."""
    text = (
        "We ordered from SILVER PINE last week. "
        "Also SILVER PINE confirmed. "
        "Partner was Copper Lake Logistics."
    )
    brands = find_brand_orgs(text)
    surfaces = {h[2] for h in brands}
    assert any(s.upper() == "SILVER PINE" for s in surfaces)
    assert any("Copper Lake" in s for s in surfaces)

    results = BrandOrgRecognizer().analyze(text, entities=["ORG"])
    out, _, _ = apply_stable_placeholders(text, results)
    assert "SILVER PINE" not in out
    assert "Copper Lake Logistics" not in out or "[ORG_" in out


def test_stable_placeholder_casefold_company():
    """Same company in different case → same placeholder."""
    text = "NORDIC WIDGETS OY met Nordic Widgets Oy again."
    r = DocumentAnonymizer(AnonymizerConfig(lang="en")).anonymize_text(
        text, lang_flag="en"
    )
    # Both forms should collapse to one ORG id when normalized
    assert "NORDIC WIDGETS OY" not in r.anonymized_text
    assert "Nordic Widgets Oy" not in r.anonymized_text
    # Prefer single id for same underlying name
    assert r.anonymized_text.count("[ORG_1]") >= 1


def test_end_to_end_mixed():
    text = (
        "Yritys NORDIC WIDGETS OY toimittaa tavaraa osoitteeseen "
        "Testikatu 12, 00100 Helsinki. "
        "Rekisterinumero XYZ-987. "
        "Lisätietoja https://www.nordic-widgets.example.fi/info "
        "ja www.example.org. Myös SILVER PINE Ab. "
        "Erillinen postinumero kentässä: 02330."
    )
    r = DocumentAnonymizer(AnonymizerConfig(lang="fi")).anonymize_text(
        text, lang_flag="fi"
    )
    out = r.anonymized_text
    for leak in (
        "NORDIC WIDGETS OY",
        "Testikatu 12, 00100 Helsinki",
        "XYZ-987",
        "00100",
        "https://www.nordic-widgets.example.fi/info",
        "www.example.org",
        "SILVER PINE",
        "02330",
    ):
        assert leak not in out, f"leaked: {leak!r} in {out!r}"
    assert "[PLATE_FI_" in out
    assert "[URL_" in out
    assert "[ORG_" in out
    assert "[STREET_" in out
    assert "[CITY_" in out
    # Standalone postcode still tagged when not part of full address line
    assert "[POSTAL_" in out


def test_form_label_not_redacted_as_location():
    """Finnish form labels must not become LOCATION (e.g. Rekisterinumero/tunniste:)."""
    text = (
        "Rekisterinumero/tunniste:\n"
        "ABC-123\n"
        "Osoite:\n"
        "Avainkierto 17a\n"
        "Postinumero ja Toimipaikka:\n"
        "02330 ESPOO\n"
    )
    r = DocumentAnonymizer(AnonymizerConfig(lang="en,fi")).anonymize_text(
        text, lang_flag="en,fi"
    )
    out = r.anonymized_text
    assert "Rekisterinumero" in out
    assert "/tunniste:" in out or "tunniste:" in out
    assert "ABC-123" not in out
    assert "Avainkierto" not in out
    assert "ESPOO" not in out
    # Must not produce Rekisterinumero → [LOCATION_x]/tunniste:
    assert not re.search(r"\[LOCATION_\d+\]/tunniste", out)


def test_postal_and_brand_mid_sentence():
    # Bare postcode + city is a LOCATION (not a leftover POSTAL + city)
    assert any(h[2] == "02330" for h in find_fi_postals("Toimitus 02330 Espoo."))
    brands = find_brand_orgs(
        "We ordered from SILVER PINE last week and SILVER PINE delivered."
    )
    assert any(h[2].upper() == "SILVER PINE" for h in brands)

    text = (
        "Tilasimme SILVER PINE -toimittajalta. "
        "Toimitusosoite on 02330 Espoo. "
        "SILVER PINE hoiti kuljetuksen. "
        "Myös BEST CARAVAN OY tarjosi. "
        "Kenttä Postinumero:02330."
    )
    r = DocumentAnonymizer(AnonymizerConfig(lang="en,fi")).anonymize_text(
        text, lang_flag="en,fi"
    )
    out = r.anonymized_text
    assert "02330" not in out
    assert "Espoo" not in out
    assert "SILVER PINE" not in out
    assert "BEST CARAVAN OY" not in out
    assert "[LOCATION_" in out or "[POSTAL_" in out
    assert "[ORG_" in out


def test_brand_rejects_legal_boilerplate_and_form_labels():
    """Legal titles and form labels must not be brands; real brands must remain."""
    for noise in (
        "Letter of Intent",
        "Memorandum of Understanding",
        "Payment IBAN",
        "European Contract Law",
        "Maine Publishing Agreement",
        "Initial Delivery Date",
    ):
        assert find_brand_orgs(noise) == [], f"should not brand: {noise!r}"

    for brand in ("SILVER PINE", "COPPER LAKE"):
        hits = find_brand_orgs(f"Partner {brand} confirmed.")
        assert any(h[2].upper() == brand for h in hits), f"missed brand {brand}: {hits}"


def test_company_strips_role_prefix():
    hits = find_companies("The Client ACME LOGISTICS LTD may escalate.")
    assert hits, hits
    assert all(not h[2].casefold().startswith("client") for h in hits), hits
    hits_fi = find_companies("Toimittaja NORDIC WIDGETS OY sitoutuu.")
    assert hits_fi, hits_fi
    assert all(not h[2].casefold().startswith("toimittaja") for h in hits_fi), hits_fi


def test_en_city_does_not_swallow_next_line_label():
    from anonymizer.anonymize.recognizers.street import find_address_hits

    text = "Address: 500 Market Street, San Francisco\nCustomer: ACME"
    cities = [h[2] for h in find_address_hits(text) if h[4] == "CITY"]
    assert cities == ["San Francisco"], cities


def test_person_false_positives_lien_manuscript():
    text = (
        "said rights are not subject to any proper agreement, lien, or other claim. "
        "loss or destruction of the Manuscript or any other documents. "
        "The Work is original."
    )
    r = DocumentAnonymizer(AnonymizerConfig(lang="en")).anonymize_text(
        text, lang_flag="en"
    )
    for token in ("lien", "Manuscript", "Work"):
        assert token in r.anonymized_text, f"over-redacted {token!r}"
    assert "lien" not in r.mapping.values()
    assert "Manuscript" not in r.mapping.values()

