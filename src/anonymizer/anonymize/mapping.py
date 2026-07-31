"""Stable entity → placeholder mapping within a document."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


_WS_RE = re.compile(r"\s+")

# Presidio / custom types → short placeholder labels
TYPE_LABELS: dict[str, str] = {
    "PERSON": "PERSON",
    "ORG": "ORG",
    "ORGANIZATION": "ORG",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "LOCATION": "LOCATION",
    "LOC": "LOCATION",
    "GPE": "LOCATION",
    "STREET": "STREET",
    "CITY": "CITY",
    "DATE_TIME": "DATE",
    "IP_ADDRESS": "IP",
    "CREDIT_CARD": "CREDIT_CARD",
    "IBAN_CODE": "IBAN",
    "US_SSN": "US_SSN",
    "US_DRIVER_LICENSE": "US_DL",
    "NRP": "NRP",
    "FI_HETU": "FI_HETU",
    "FI_BUSINESS_ID": "FI_BUSINESS_ID",
    # VAT / ALV: VAT_FI_n  e.g. FI28567738 → [VAT_FI_1]
    "FI_VAT": "VAT_FI",
    # Plates: PLATE_{COUNTRY}_{n}  e.g. Finnish ABC-123 → [PLATE_FI_1]
    "FI_LICENSE_PLATE": "PLATE_FI",
    "FI_POSTAL_CODE": "POSTAL",
    "VEHICLE_VIN": "VIN",
    "URL": "URL",
    "CUSTOM": "CUSTOM",
}


def normalize_entity_text(text: str) -> str:
    return _WS_RE.sub(" ", text.strip()).casefold()


def placeholder_label(entity_type: str) -> str:
    """Return placeholder type label (e.g. PERSON, PLATE_FI).

    Vehicle plates use ``PLATE_{COUNTRYCODE}`` so numbers look like
    ``[PLATE_FI_1]``. Unknown plate entities named ``XX_LICENSE_PLATE``
    map to ``PLATE_XX`` automatically.
    """
    key = entity_type.upper()
    if key in TYPE_LABELS:
        return TYPE_LABELS[key]
    # e.g. SE_LICENSE_PLATE → PLATE_SE
    if key.endswith("_LICENSE_PLATE"):
        country = key[: -len("_LICENSE_PLATE")]
        if country:
            return f"PLATE_{country}"
    return key


@dataclass
class EntityMap:
    """Assigns stable placeholders like [PERSON_1] per normalized surface form."""

    _counters: dict[str, int] = field(default_factory=dict)
    # (label, normalized_text) -> placeholder
    _forward: dict[tuple[str, str], str] = field(default_factory=dict)
    # placeholder -> original first-seen text
    reverse: dict[str, str] = field(default_factory=dict)

    def get_or_assign(self, entity_type: str, text: str) -> str:
        label = placeholder_label(entity_type)
        key = (label, normalize_entity_text(text))
        if key in self._forward:
            return self._forward[key]
        n = self._counters.get(label, 0) + 1
        self._counters[label] = n
        placeholder = f"[{label}_{n}]"
        self._forward[key] = placeholder
        self.reverse[placeholder] = text
        return placeholder

    def counts_by_type(self) -> dict[str, int]:
        """Count unique entities assigned per placeholder label."""
        counts: dict[str, int] = {}
        for (label, _), _ in self._forward.items():
            counts[label] = counts.get(label, 0) + 1
        return counts
