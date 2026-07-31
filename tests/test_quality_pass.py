"""Quality pass: names, postal FPs, ORG headers, stems, phones, headers."""

from __future__ import annotations

from anonymizer.anonymize.config import AnonymizerConfig
from anonymizer.anonymize.engine import DocumentAnonymizer
from anonymizer.anonymize.org_stems import company_stems_from_org_surface, expand_org_stems_in_text
from anonymizer.anonymize.recognizers.fi_phone import find_fi_phones
from anonymizer.anonymize.recognizers.fi_postal import find_fi_postals
from anonymizer.anonymize.recognizers.person_name import find_person_names
from anonymizer.anonymize.recognizers.street import find_address_hits
from anonymizer.extract.headers import filter_running_headers
from anonymizer.models import BlockKind, TextBlock


def test_city_after_nbsp_with_postcode():
    """PDF NBSP between postcode and city must still yield CITY."""
    from anonymizer.anonymize.recognizers.street import find_address_hits

    text = (
        "Osoite: Avainkierto 11\u00a005840\u00a0Hyvinkää "
        "Puhelinnumero:\u00a00108324500"
    )
    hits = find_address_hits(text)
    assert any(h[4] == "CITY" and "Hyvinkää" in h[2] for h in hits), hits
    assert any(h[4] == "FI_POSTAL_CODE" and h[2] == "05840" for h in hits), hits
    cfg = AnonymizerConfig(mode="strict", lang="fi")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    assert "Hyvinkää" not in r.anonymized_text
    assert "[CITY_" in r.anonymized_text


def test_last_first_person_name():
    text = "Nimi:\nKorhonen, Maija"
    hits = find_person_names(text)
    assert any("Korhonen" in h[2] and "Maija" in h[2] for h in hits), hits
    cfg = AnonymizerConfig(mode="strict", lang="fi")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    assert "Korhonen" not in r.anonymized_text
    assert "Maija" not in r.anonymized_text
    assert "[PERSON_" in r.anonymized_text


def test_km_limit_not_postcode_city():
    text = (
        "Kilometri/käyttöaikaraja:\n"
        "23333\n\n"
        "Ylikilometriveloitus €/km:\n"
        "0.40\n"
    )
    assert find_fi_postals(text) == []
    cities = [h for h in find_address_hits(text) if h[4] == "CITY"]
    assert not any("Ylikilometri" in h[2] for h in cities), cities
    cfg = AnonymizerConfig(mode="strict", lang="fi")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    assert "23333" in r.anonymized_text
    assert "Ylikilometriveloitus" in r.anonymized_text


def test_section_headers_not_org():
    for title in (
        "LISÄPALVELUT JA LISÄPALVELUVELOITUKSET",
        "LEASINGVUOKRAT YHTEENSÄ",
        "Force Majeure",
        "green card",
        "Virheellinen Leasingkohde",
        "ETÄMYYNNIN JA KOTIMYYNNIN PERUUTUSEHDOT JA -OHJEET",
    ):
        cfg = AnonymizerConfig(mode="strict", lang="fi")
        cfg.apply_mode()
        r = DocumentAnonymizer(cfg).anonymize_text(title, lang_flag="fi")
        assert title.split()[0][:6] in r.anonymized_text or title[:10] in r.anonymized_text, (
            title,
            r.anonymized_text,
            r.mapping,
        )
        assert not any(
            v == title or title.startswith(v)
            for k, v in r.mapping.items()
            if k.startswith("[ORG_")
        ), (title, r.mapping)


def test_asiakas_not_org():
    text = "Asiakas on velvollinen vakuuttamaan leasingkohteen."
    cfg = AnonymizerConfig(mode="strict", lang="fi")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    assert "Asiakas" in r.anonymized_text
    assert not any(v == "Asiakas" for v in r.mapping.values())


def test_company_stem_propagation():
    stems = company_stems_from_org_surface("LähiTapiola Rahoitus Oy")
    assert any("LähiTapiola" == s for s in stems), stems
    text = (
        "LähiTapiola Rahoitus Oy ostaa ajoneuvon. "
        "LähiTapiolan tehtävänä on rahoitus. "
        '("LähiTapiola") merkitään omistajaksi.'
    )
    cfg = AnonymizerConfig(mode="strict", lang="fi")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    assert "LähiTapiola Rahoitus Oy" not in r.anonymized_text
    # Inflected / short forms should go too
    assert "LähiTapiolan" not in r.anonymized_text
    assert "LähiTapiola" not in r.anonymized_text
    assert "[ORG_" in r.anonymized_text


def test_fi_service_phone_and_nbsp():
    assert find_fi_phones("0108324500")
    assert find_fi_phones("010 832 4500")
    assert find_fi_phones("Puhelinnumero:\xa0108324500")
    text = "Puhelinnumero:\xa0108324500"
    cfg = AnonymizerConfig(mode="strict", lang="fi")
    cfg.apply_mode()
    r = DocumentAnonymizer(cfg).anonymize_text(text, lang_flag="fi")
    assert "108324500" not in r.anonymized_text
    assert "[PHONE_" in r.anonymized_text


def test_filter_running_headers():
    blocks = [
        TextBlock(text="Doc 109 / 1.0 / 2505301102", kind=BlockKind.PARAGRAPH, page=1),
        TextBlock(text="1 (5)", kind=BlockKind.PARAGRAPH, page=1),
        TextBlock(
            text="LähiTapiola Rahoitus Oy Revontulenkuja 1 02100 Espoo",
            kind=BlockKind.PARAGRAPH,
            page=1,
        ),
        TextBlock(
            text="Sopimusnumero:\n70039769\nLuottopäätösnumero:\n953447",
            kind=BlockKind.PARAGRAPH,
            page=1,
        ),
        TextBlock(text="ASIAKAS", kind=BlockKind.PARAGRAPH, page=1),
        TextBlock(text="Nimi:\nTesti", kind=BlockKind.PARAGRAPH, page=1),
        TextBlock(
            text="Y-tunnus:\n1824257-7",  # unique form field — keep
            kind=BlockKind.PARAGRAPH,
            page=1,
        ),
        TextBlock(text="Doc 109 / 1.0 / 2505301102", kind=BlockKind.PARAGRAPH, page=2),
        TextBlock(text="2 (5)", kind=BlockKind.PARAGRAPH, page=2),
        TextBlock(
            text="LähiTapiola Rahoitus Oy Revontulenkuja 1 02100 Espoo",
            kind=BlockKind.PARAGRAPH,
            page=2,
        ),
        TextBlock(
            text="Sopimusnumero:\n70039769\nLuottopäätösnumero:\n953447",
            kind=BlockKind.PARAGRAPH,
            page=2,
        ),
        TextBlock(
            text="LähiTapiola Rahoitus Oy Revontulenkuja 1 02100 Espoo",
            kind=BlockKind.PARAGRAPH,
            page=3,
        ),
        TextBlock(
            text="Sopimusnumero:\n70039769\nLuottopäätösnumero:\n953447",
            kind=BlockKind.PARAGRAPH,
            page=3,
        ),
        TextBlock(
            text="Y-tunnus: 2856773-8 ALV-numero: FI28567738",
            kind=BlockKind.PARAGRAPH,
            page=1,
        ),
        TextBlock(
            text="Y-tunnus: 2856773-8 ALV-numero: FI28567738",
            kind=BlockKind.PARAGRAPH,
            page=2,
        ),
        TextBlock(
            text="Y-tunnus: 2856773-8 ALV-numero: FI28567738",
            kind=BlockKind.PARAGRAPH,
            page=3,
        ),
        TextBlock(
            text="www.example.fi https://example.fi/x",
            kind=BlockKind.PARAGRAPH,
            page=1,
        ),
        TextBlock(
            text="www.example.fi https://example.fi/x",
            kind=BlockKind.PARAGRAPH,
            page=2,
        ),
        TextBlock(text="Puh: 09 478 44 501", kind=BlockKind.PARAGRAPH, page=1),
        TextBlock(text="Puh: 09 478 44 501", kind=BlockKind.PARAGRAPH, page=2),
        TextBlock(text="Puh: 09 478 44 501", kind=BlockKind.PARAGRAPH, page=3),
        TextBlock(
            text="ETÄMYYNNIN JA KOTIMYYNNIN PERUUTUSEHDOT JA -OHJEET\nTekstiä.",
            kind=BlockKind.PARAGRAPH,
            page=3,
        ),
    ]
    kept = filter_running_headers(blocks, keep_headers=False)
    texts = [b.text for b in kept]
    assert not any(t.startswith("Doc ") for t in texts)
    assert not any(t.endswith("(5)") for t in texts)
    assert not any("Revontulenkuja" in t for t in texts)
    assert not any("Sopimusnumero" in t for t in texts)
    assert not any("2856773-8" in t for t in texts)
    assert not any(t.startswith("Puh:") for t in texts)
    assert not any("www.example" in t for t in texts)
    assert "ASIAKAS" in texts
    assert any("1824257-7" in t for t in texts)  # unique form Y-tunnus kept
    assert any("ETÄMYYNNIN" in t for t in texts)

    kept_all = filter_running_headers(blocks, keep_headers=True)
    assert len(kept_all) == len(blocks)


def test_stem_expand_unit():
    text = "LähiTapiolan ja BEST-CARAVAN OY välillä."
    stems = ["LähiTapiola", "BEST-CARAVAN"]
    hits = expand_org_stems_in_text(text, stems)
    surfaces = [text[h.start : h.end] for h in hits]
    assert any("LähiTapiolan" in s or s.startswith("LähiTapiola") for s in surfaces)
