"""Domain-adapted lexicons for legal/commercial EN+FI text.

These are morphological / role / form-label / collocation sets — **not**
catalogs of real companies or people (see Agents.md). Used by engine FP
filters, brand heuristics, org-stem hygiene, and default allowlists.

Optional YAML ``lexicon_extra`` merges into a :class:`LexiconView` at config
load (see ``config.example.yaml``). Built-in sets remain the offline default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

# ---------------------------------------------------------------------------
# Contract party roles (surfaces, casefold) — single-token party labels
# ---------------------------------------------------------------------------
CONTRACT_ROLES: frozenset[str] = frozenset(
    {
        # FI — commercial / lease / insurance parties
        "asiakas",
        "myyjä",
        "ostaja",
        "toimittaja",
        "tilaaja",
        "vuokralainen",
        "vuokranantaja",
        "osapuoli",
        "edustaja",
        "asiamies",
        "yhteyshenkilö",
        "yhteyshenkilo",
        "allekirjoittaja",
        "käyttäjä",
        "kayttaja",
        "omistaja",
        "työntekijä",
        "tyontekija",
        "työnantaja",
        "tyonantaja",
        "vakuutuksenottaja",
        "vakuutuksenantaja",
        "vakuutettu",
        "maksaja",
        "saaja",
        "velallinen",
        "velkoja",
        "urakoitsija",
        "alihankkija",
        "konsultti",
        "neuvonantaja",
        # EN — commercial / lease / insurance parties
        "client",
        "customer",
        "seller",
        "buyer",
        "supplier",
        "provider",
        "vendor",
        "contractor",
        "subcontractor",
        "author",
        "publisher",
        "lessor",
        "lessee",
        "landlord",
        "tenant",
        "party",
        "parties",
        "insured",
        "insurer",
        "policyholder",
        "broker",
        "agent",
        "signatory",
        "principal",
        "licensee",
        "licensor",
        "consultant",
        "employee",
        "employer",
        "guarantor",
        "beneficiary",
        "payee",
        "payer",
        "owner",
        "user",
        "representative",
        "attorney",
        "counsel",
    }
)

# Leading role tokens stripped from ORG spans / brands
ORG_ROLE_PREFIXES: frozenset[str] = CONTRACT_ROLES | frozenset(
    {
        "brand",
        "brands",
        "brändi",
        "brändiä",
        "partner",
        "partners",
        "kumppani",
    }
)

# ---------------------------------------------------------------------------
# Legal / insurance / privacy collocations (full surface, casefold)
# ---------------------------------------------------------------------------
LEGAL_PHRASES: frozenset[str] = frozenset(
    {
        # EN
        "force majeure",
        "green card",
        "green cardiin",
        "letter of intent",
        "memorandum of understanding",
        "terms and conditions",
        "terms of service",
        "privacy policy",
        "data protection",
        "personal data",
        "governing law",
        "non-disclosure",
        "non disclosure",
        "confidential information",
        "intellectual property",
        "indemnification",
        "limitation of liability",
        "service level agreement",
        "data processing agreement",
        "business day",
        "calendar day",
        "initial delivery date",
        "delivery date",
        "effective date",
        "termination date",
        "notice period",
        "good faith",
        "best efforts",
        "arm's length",
        "arms length",
        "without prejudice",
        "subject to contract",
        "all rights reserved",
        "confidential",
        # FI
        "henkilötiedot",
        "henkilotiedot",
        "sopimusehdot",
        "yleiset ehdot",
        "yleiset sopimusehdot",
        "erityisehdot",
        "peruutusehdot",
        "salassapito",
        "liikesalaisuus",
        "sovellettava laki",
        "riidanratkaisu",
        "vahingonkorvaus",
        "vastuunrajoitus",
        "henkilötietojen käsittely",
        "henkilotietojen kasittely",
        "tietosuoja",
        "tietosuojaseloste",
        "sopimusrikkomus",
        "sopimussakko",
        "irtisanomisaika",
        "voimaantulopäivä",
        "voimaantulopaiva",
        "päättymispäivä",
        "paattymispaiva",
        "maksuehdot",
        "toimitusehdot",
        "vastuu",
        "velvollisuudet",
        "oikeudet ja velvollisuudet",
        "hallituksen jäsen",
        "hallituksen jasen",
        "toimitusjohtaja",
    }
)

# Document / schedule title tails (last token of a heading-like surface)
DOC_TITLE_TAILS: frozenset[str] = frozenset(
    {
        "agreement",
        "contract",
        "policy",
        "addendum",
        "amendment",
        "schedule",
        "appendix",
        "annex",
        "exhibit",
        "caselist",
        "summaries",
        "summary",
        "warranty",
        "warranties",
        "indemnity",
        "definitions",
        "recitals",
        "whereas",
        "ehdot",
        "peruutusehdot",
        "veloitus",
        "veloitusukset",
        "palvelut",
        "yhteensä",
        "yhteensa",
        "majeure",
        "card",
        "cardiin",
        "sopimus",
        "liite",
        "liitteet",
        "osio",
        "luku",
        "määritelmät",
        "maaritelmat",
        "vastuut",
        "veloitusperusteet",
        "perusteet",
        "menettely",
        "menettelyt",
        "ohjeet",
        "guidelines",
        "principles",
    }
)

# Generic first tokens that must not become org stems alone
WEAK_ORG_STEM_TOKENS: frozenset[str] = frozenset(
    {
        "best",
        "global",
        "nordic",
        "nordisk",
        "international",
        "european",
        "national",
        "general",
        "special",
        "standard",
        "premium",
        "new",
        "first",
        "group",
        "holding",
        "holdings",
        "services",
        "service",
        "solutions",
        "solution",
        "systems",
        "system",
        "finland",
        "suomi",
        "helsinki",
        "company",
        "companies",
        "yhtiö",
        "yhtio",
        "oyj",
        "limited",
        "universal",
        "united",
        "common",
        "public",
        "private",
        "digital",
        "smart",
        "modern",
        "advanced",
        "professional",
        "commercial",
        "corporate",
        "regional",
        "local",
        "central",
        "paikallinen",
        "kansallinen",
        "eurooppalainen",
        "pohjoismainen",
    }
) | CONTRACT_ROLES | DOC_TITLE_TAILS

# Legalish lemmas / tokens (boilerplate ORG/PERSON noise)
LEGALISH_TOKENS: frozenset[str] = frozenset(
    {
        "agreement",
        "publishing",
        "rights",
        "delivery",
        "date",
        "initial",
        "author",
        "changes",
        "warranties",
        "warranty",
        "indemnity",
        "indemnification",
        "limitation",
        "liability",
        "information",
        "grant",
        "section",
        "article",
        "clause",
        "schedule",
        "appendix",
        "promotion",
        "distribution",
        "copyright",
        "manuscript",
        "work",
        "new",
        "letter",
        "intent",
        "memorandum",
        "understanding",
        "contract",
        "law",
        "case",
        "cases",
        "summaries",
        "summary",
        "basics",
        "convention",
        "sale",
        "international",
        "european",
        "united",
        "nations",
        "nation",
        "archive",
        "internet",
        "caselist",
        "list",
        "principles",
        "school",
        "university",
        "college",
        "institute",
        "wikipedia",
        "wiki",
        "leasingkohde",
        "sopimus",
        "sopimusehdot",
        "ehdot",
        "liite",
        "osapuoli",
        "velvollisuus",
        "vakuutus",
        "korvaus",
        "maksu",
        "veloitus",
        "vuokra",
        "palvelu",
        "palvelut",
        # insurance / leasing / finance
        "premium",
        "deductible",
        "excess",
        "claim",
        "claims",
        "coverage",
        "policy",
        "policies",
        "liability",
        "omavastuu",
        "vakuutusmaksu",
        "leasing",
        "kilometri",
        "yliajo",
        "ylikilometri",
        "kilometriraja",
        "vakuutuskausi",
        "korvaushakemus",
        "vahinko",
        "riski",
        "risk",
        "recitals",
        "definitions",
        "whereas",
        "hereby",
        "hereof",
        "herein",
        "shall",
        "confidential",
        "salassapito",
        "liikesalaisuus",
        "tietosuoja",
        "käsittely",
        "kasittely",
        "vastuu",
        "rajoitus",
        "sanktio",
        "sanktiot",
        "määritelmä",
        "maaritelma",
        "määritelmät",
        "maaritelmat",
    }
)

FORMISH_TOKENS: frozenset[str] = frozenset(
    {
        "payment",
        "iban",
        "email",
        "e-mail",
        "phone",
        "address",
        "website",
        "contact",
        "account",
        "invoice",
        "reference",
        "number",
        "code",
        "field",
        "label",
        "source",
        "url",
        "http",
        "https",
        "name",
        "legal",
        "office",
        "registered",
        "delivery",
        "vehicle",
        "network",
        "endpoint",
        "person",
        "business",
        "secondary",
        "site",
        "also",
        "trading",
        "customer",
        "supplier",
        "annex",
        "synthetic",
        "osoite",
        "puhelin",
        "sähköposti",
        "sahkoposti",
        "nimi",
        "viite",
        "lasku",
        "tili",
        "numero",
        "tunnus",
        "tunniste",
        "postinumero",
        "toimipaikka",
        "matkapuhelin",
        "fax",
        "faksi",
        "kotisivu",
        "verkkosivu",
        "y-tunnus",
        "alv",
        "vat",
        "bic",
        "swift",
        "rekisterinumero",
        "rekisteritunnus",
        "asiakasnumero",
        "tilausnumero",
        "laskunumero",
        "viitenumero",
        "päivämäärä",
        "paivamaara",
        "allekirjoitus",
        "signature",
        "title",
        "titteli",
        "position",
        "asema",
    }
)

# Commercial LOCATION / single-token compound tails (FI office docs)
COMMERCIAL_LOC_SUFFIX = re.compile(
    r"(?i)(veloitus|maksu|palkkio|vuokra|ehdot|palvelut|yhteens[aä]|raja|"
    r"korvaus|vakuutus|maksuerä|erä|omavastuu|vakuutusmaksu|"
    r"kilometriveloitus|ylikilometriveloitus|kilometriraja|"
    r"leasingmaksu|kuukausimaksu|käyttömaksu|kayttomaksu)$",
    re.UNICODE,
)

# Cue tokens for cheap left/right boilerplate neighbourhood (casefold)
BOILERPLATE_CONTEXT_CUES: frozenset[str] = frozenset(
    {
        "section",
        "article",
        "clause",
        "schedule",
        "appendix",
        "annex",
        "exhibit",
        "whereas",
        "hereby",
        "hereof",
        "pursuant",
        "agreement",
        "contract",
        "liite",
        "kohta",
        "luku",
        "pykälä",
        "pykala",
        "sopimus",
        "sopimusehdot",
        "ehto",
        "ehdot",
        "määritelmä",
        "maaritelma",
        "määritelmät",
        "maaritelmat",
    }
)

# ---------------------------------------------------------------------------
# Default allowlist seeds (exact surfaces users rarely want redacted)
# ---------------------------------------------------------------------------
DEFAULT_ALLOWLIST_SEEDS: list[str] = [
    # IDs / tax field labels
    "Y-tunnus",
    "Y tunnus",
    "Hetu",
    "Henkilötunnus",
    "ALV-numero",
    "ALV numero",
    "ALV",
    "VAT",
    "IBAN",
    "BIC",
    "SWIFT",
    # Contact field labels
    "Email",
    "E-mail",
    "Sähköposti",
    "Phone",
    "Puhelin",
    "Mobile",
    "Fax",
    # Address field labels
    "Address",
    "Osoite",
    "Street",
    "Postinumero",
    "Toimipaikka",
    "City",
    "Country",
    "Maa",
    # Form meta
    "Name",
    "Nimi",
    "Reference",
    "Viite",
    "Invoice",
    "Lasku",
    "Account",
    "Yhteyshenkilö",
    "Rekisterinumero",
    "Rekisterinumero/tunniste",
    # Contract roles (short surfaces)
    "Asiakas",
    "Myyjä",
    "Ostaja",
    "Toimittaja",
    "Tilaaja",
    "Osapuoli",
    "Vuokralainen",
    "Vuokranantaja",
    "Vakuutuksenottaja",
    "Vakuutuksenantaja",
    "Client",
    "Customer",
    "Supplier",
    "Seller",
    "Buyer",
    "Insurer",
    "Insured",
    "Policyholder",
    "Lessor",
    "Lessee",
    # Legal collocations
    "Force Majeure",
    "Letter of Intent",
    "Green Card",
    "Governing Law",
    "Memorandum of Understanding",
    "Terms and Conditions",
    "Privacy Policy",
    "Confidential Information",
    "Intellectual Property",
    "Sovellettava laki",
    "Yleiset sopimusehdot",
    "Salassapito",
    "Vastuunrajoitus",
]


# ---------------------------------------------------------------------------
# LexiconView — immutable snapshot (built-ins ∪ optional YAML extra)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LexiconView:
    """Immutable domain lexicon used by FP filters and stem hygiene."""

    roles: frozenset[str] = field(default_factory=lambda: CONTRACT_ROLES)
    legal_phrases: frozenset[str] = field(default_factory=lambda: LEGAL_PHRASES)
    doc_title_tails: frozenset[str] = field(default_factory=lambda: DOC_TITLE_TAILS)
    weak_org_stems: frozenset[str] = field(default_factory=lambda: WEAK_ORG_STEM_TOKENS)
    legalish_tokens: frozenset[str] = field(default_factory=lambda: LEGALISH_TOKENS)
    formish_tokens: frozenset[str] = field(default_factory=lambda: FORMISH_TOKENS)
    org_role_prefixes: frozenset[str] = field(default_factory=lambda: ORG_ROLE_PREFIXES)
    boilerplate_cues: frozenset[str] = field(
        default_factory=lambda: BOILERPLATE_CONTEXT_CUES
    )
    commercial_loc_suffix: re.Pattern[str] = field(
        default_factory=lambda: COMMERCIAL_LOC_SUFFIX
    )


def builtin_lexicon() -> LexiconView:
    """Return the offline built-in lexicon (no YAML extras)."""
    return LexiconView()


def _norm_items(items: Iterable[Any] | None) -> frozenset[str]:
    if not items:
        return frozenset()
    out: set[str] = set()
    for x in items:
        if x is None:
            continue
        s = normalize_surface(str(x))
        if s:
            out.add(s)
    return frozenset(out)


def merge_lexicon_extra(
    extra: Mapping[str, Any] | None,
    *,
    base: LexiconView | None = None,
) -> LexiconView:
    """Merge YAML ``lexicon_extra`` mapping into *base* (default: built-ins).

    Recognised keys (lists of strings, casefolded on merge)::

        roles, legal_phrases, legalish_tokens, formish_tokens,
        weak_org_stems, doc_title_tails, org_role_prefixes, boilerplate_cues
    """
    root = base or builtin_lexicon()
    if not extra:
        return root
    if not isinstance(extra, Mapping):
        return root

    roles = root.roles | _norm_items(extra.get("roles"))
    legal_phrases = root.legal_phrases | _norm_items(extra.get("legal_phrases"))
    legalish = root.legalish_tokens | _norm_items(extra.get("legalish_tokens"))
    formish = root.formish_tokens | _norm_items(extra.get("formish_tokens"))
    weak = root.weak_org_stems | _norm_items(extra.get("weak_org_stems"))
    tails = root.doc_title_tails | _norm_items(extra.get("doc_title_tails"))
    prefixes = root.org_role_prefixes | _norm_items(extra.get("org_role_prefixes")) | roles
    cues = root.boilerplate_cues | _norm_items(extra.get("boilerplate_cues"))
    # weak stems always absorb roles + title tails (same as built-in composition)
    weak = weak | roles | tails

    return LexiconView(
        roles=roles,
        legal_phrases=legal_phrases,
        doc_title_tails=tails,
        weak_org_stems=weak,
        legalish_tokens=legalish,
        formish_tokens=formish,
        org_role_prefixes=prefixes,
        boilerplate_cues=cues,
        commercial_loc_suffix=root.commercial_loc_suffix,
    )


def normalize_surface(s: str) -> str:
    return s.strip().strip("\"'()«»").casefold()


def is_contract_role_surface(
    surface: str, lexicon: LexiconView | None = None
) -> bool:
    lex = lexicon or builtin_lexicon()
    return normalize_surface(surface) in lex.roles


def is_legal_phrase_surface(
    surface: str, lexicon: LexiconView | None = None
) -> bool:
    lex = lexicon or builtin_lexicon()
    return normalize_surface(surface) in lex.legal_phrases


def is_role_or_legal_surface(
    surface: str, lexicon: LexiconView | None = None
) -> bool:
    return is_contract_role_surface(surface, lexicon) or is_legal_phrase_surface(
        surface, lexicon
    )


def is_weak_org_stem(token: str, lexicon: LexiconView | None = None) -> bool:
    lex = lexicon or builtin_lexicon()
    t = normalize_surface(token)
    if len(t) < 4:
        return True
    if t in lex.weak_org_stems or t in lex.legalish_tokens or t in lex.formish_tokens:
        return True
    return False


def tokens_all_domain_noise(
    tokens: list[str], lexicon: LexiconView | None = None
) -> bool:
    """True if every token is role/legalish/formish/title-tail (no proper name)."""
    lex = lexicon or builtin_lexicon()
    if not tokens:
        return True
    stop = {
        "of",
        "and",
        "the",
        "for",
        "to",
        "a",
        "an",
        "on",
        "in",
        "ja",
        "tai",
        "sekä",
        "seka",
        "or",
        "with",
        "by",
        "as",
    }
    for raw in tokens:
        t = normalize_surface(raw).strip(".,;:'\"")
        if not t:
            continue
        if t in lex.roles or t in lex.legalish_tokens or t in lex.formish_tokens:
            continue
        if t in lex.doc_title_tails:
            continue
        if t in stop:
            continue
        return False
    return True
