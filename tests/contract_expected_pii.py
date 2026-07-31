"""Ground-truth PII / identifier strings that must not appear after anonymization.

All values are synthetic. Keep this list in sync when extending contract_*.txt fixtures.
"""

from __future__ import annotations

# Shared / cross-cutting
SHARED_MUST_REDACT: list[str] = [
    "NORDIC WIDGETS OY",
    "SILVER PINE",
    "ACME LOGISTICS",
    "ABC-123",
    "https://www.nordic-widgets.example.com/services",
    "https://www.nordic-widgets.example.fi/palvelut",
    "www.silver-pine.example.org",
    "www.silver-pine.example.fi",
    "GB29 NWBK 6016 1331 9268 19",
]

EN_MUST_REDACT: list[str] = SHARED_MUST_REDACT + [
    "Jordan Avery Blake",
    "Morgan Ellis Quinn",
    "jordan.blake@nordic-widgets.example.com",
    "morgan.quinn@acme-logistics.example.com",
    "+1 (415) 555-0199",
    "+44 20 7946 0958",
    "500 Market Street",
    "12 Baker Street",
    "203.0.113.42",
    "ACME LOGISTICS LTD",
]

FI_MUST_REDACT: list[str] = SHARED_MUST_REDACT + [
    "ACME LOGISTICS AB",
    "COPPER LAKE",
    "Maija Korhonen",
    "Pekka Nieminen",
    "maija.korhonen@nordic-widgets.example.fi",
    "pekka.nieminen@acme-logistics.example.fi",
    "+358 50 987 6543",
    "040 123 4567",
    "+358 (0) 9 1234 567",
    "0737546-2",
    "FI07375462",
    "131052-308T",
    "Mannerheimintie 12",
    "Testikatu 99",
    "Aleksanterinkatu 1",
    "00100",
    "02330",
    "FI21 1234 5600 0007 85",
]
