"""Configuration defaults and YAML loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_ENTITIES: list[str] = [
    "PERSON",
    "ORG",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "LOCATION",
    "IP_ADDRESS",
    "CREDIT_CARD",
    "IBAN_CODE",
    "FI_HETU",
    "FI_BUSINESS_ID",
]

OPTIONAL_DATE_ENTITY = "DATE_TIME"

SPACY_MODELS = {
    "en": "en_core_web_lg",
    "fi": "fi_core_news_lg",
}

# Lighter fallbacks if large models missing
SPACY_FALLBACKS = {
    "en": ["en_core_web_md", "en_core_web_sm"],
    "fi": ["fi_core_news_md", "fi_core_news_sm"],
}


@dataclass
class DenylistEntry:
    text: str
    entity_type: str = "ORG"


# Common false positives (labels / generic words, not PII)
DEFAULT_ALLOWLIST: list[str] = [
    "Y-tunnus",
    "Y tunnus",
    "Hetu",
    "Henkilötunnus",
    "Meeting",
    "Notes",
    "Contact",
    "Email",
    "Phone",
    "Date",
    "Appendix",
    "Liite",
    "Sopimus",
    "Contract",
]


@dataclass
class AnonymizerConfig:
    score_threshold: float = 0.5
    entities: list[str] = field(default_factory=lambda: list(DEFAULT_ENTITIES))
    allowlist: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWLIST))
    denylist: list[DenylistEntry] = field(default_factory=list)
    lang: str = "auto"
    include_dates: bool = False

    def effective_entities(self) -> list[str]:
        ents = list(self.entities)
        if self.include_dates and OPTIONAL_DATE_ENTITY not in ents:
            ents.append(OPTIONAL_DATE_ENTITY)
        return ents


def load_config(path: Path | None) -> AnonymizerConfig:
    cfg = AnonymizerConfig()
    if path is None:
        return cfg
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "score_threshold" in data:
        cfg.score_threshold = float(data["score_threshold"])
    if "entities" in data and data["entities"]:
        cfg.entities = list(data["entities"])
    if "allowlist" in data and data["allowlist"] is not None:
        # YAML allowlist replaces defaults when provided (including empty list)
        cfg.allowlist = [str(x) for x in data["allowlist"]]
    if "denylist" in data and data["denylist"]:
        entries: list[DenylistEntry] = []
        for item in data["denylist"]:
            if isinstance(item, str):
                entries.append(DenylistEntry(text=item, entity_type="ORG"))
            elif isinstance(item, dict):
                entries.append(
                    DenylistEntry(
                        text=str(item.get("text", "")),
                        entity_type=str(item.get("entity_type", "ORG")),
                    )
                )
        cfg.denylist = [e for e in entries if e.text]
    if "lang" in data and data["lang"]:
        cfg.lang = str(data["lang"])
    if "include_dates" in data:
        cfg.include_dates = bool(data["include_dates"])
    return cfg
