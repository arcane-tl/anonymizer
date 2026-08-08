"""Domain-adapted lexicons for legal/commercial EN+FI text.

These are morphological / role / form-label / collocation sets — **not**
catalogs of real companies or people (see Agents.md). Used by engine FP
filters, brand heuristics, org-stem hygiene, and default allowlists.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Contract party roles (surfaces, casefold)
# ---------------------------------------------------------------------------
CONTRACT_ROLES: frozenset[str] = frozenset(
    {
        "asiakas",
        "myyjä",
        "ostaja",
        "toimittaja",
        "tilaaja",
        "vuokralainen",
        "vuokranantaja",
        "osapuoli",
        "client",
        "customer",
        "seller",
        "buyer",
        "supplier",
        "provider",
        "vendor",
        "contractor",
        "author",
        "publisher",
        "lessor",
        "lessee",
        "landlord",
        "tenant",
        "party",
        "parties",
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
    }
)

# ---------------------------------------------------------------------------
# Legal / insurance collocations (full surface, casefold)
# ---------------------------------------------------------------------------
LEGAL_PHRASES: frozenset[str] = frozenset(
    {
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
        "henkilötiedot",
        "sopimusehdot",
        "yleiset ehdot",
        "erityisehdot",
        "peruutusehdot",
    }
)

# Document / schedule title tails (last token)
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
        "caselist",
        "summaries",
        "ehdot",
        "peruutusehdot",
        "veloitus",
        "veloitusukset",
        "palvelut",
        "yhteensä",
        "majeure",
        "card",
        "cardiin",
        "sopimus",
        "liite",
        "liitteet",
        "osio",
        "luku",
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
    }
) | CONTRACT_ROLES | DOC_TITLE_TAILS

# Legalish lemmas / tokens (boilerplate ORG/PERSON noise) — EN-heavy, shared
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
        "indemnity",
        "grant",
        "section",
        "article",
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
    }
)

# Commercial LOCATION / single-token compound tails
COMMERCIAL_LOC_SUFFIX = re.compile(
    r"(?i)(veloitus|maksu|palkkio|vuokra|ehdot|palvelut|yhteens[aä]|raja|"
    r"korvaus|vakuutus|maksuerä|erä)$",
    re.UNICODE,
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
    # Contract roles (short surfaces)
    "Asiakas",
    "Myyjä",
    "Ostaja",
    "Toimittaja",
    "Tilaaja",
    "Osapuoli",
    "Client",
    "Customer",
    "Supplier",
    "Seller",
    "Buyer",
    # Legal collocations
    "Force Majeure",
    "Letter of Intent",
    "Green Card",
]


def normalize_surface(s: str) -> str:
    return s.strip().strip("\"'()«»").casefold()


def is_contract_role_surface(surface: str) -> bool:
    return normalize_surface(surface) in CONTRACT_ROLES


def is_legal_phrase_surface(surface: str) -> bool:
    return normalize_surface(surface) in LEGAL_PHRASES


def is_weak_org_stem(token: str) -> bool:
    t = normalize_surface(token)
    if len(t) < 4:
        return True
    if t in WEAK_ORG_STEM_TOKENS or t in LEGALISH_TOKENS or t in FORMISH_TOKENS:
        return True
    return False


def tokens_all_domain_noise(tokens: list[str]) -> bool:
    """True if every token is role/legalish/formish/title-tail (no proper name)."""
    if not tokens:
        return True
    for raw in tokens:
        t = normalize_surface(raw).strip(".,;:'\"")
        if not t:
            continue
        if t in CONTRACT_ROLES or t in LEGALISH_TOKENS or t in FORMISH_TOKENS:
            continue
        if t in DOC_TITLE_TAILS:
            continue
        if t in {"of", "and", "the", "for", "to", "a", "an", "on", "in", "ja", "tai", "sekä"}:
            continue
        return False
    return True
