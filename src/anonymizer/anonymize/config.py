"""Configuration defaults, mode presets, and YAML loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Entity presets per operating mode
# ---------------------------------------------------------------------------

# strict (default): full scrub — current product behaviour
STRICT_ENTITIES: list[str] = [
    "PERSON",
    "ORG",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "LOCATION",  # residual geo from NER
    "STREET",  # structured street + house
    "CITY",  # locality next to postcode / address patterns
    "URL",
    "IP_ADDRESS",
    "CREDIT_CARD",
    "IBAN_CODE",
    "FI_HETU",
    "FI_BUSINESS_ID",
    "FI_VAT",  # ALV-numero / Finnish VAT ID (FI + 8 digits)
    "FI_LICENSE_PLATE",
    "FI_POSTAL_CODE",
    "VEHICLE_VIN",  # 17-char VIN / valmistenumero (strict only)
]

# standard: identity-focused — people, contact, IDs, addresses; not companies/countries
STANDARD_ENTITIES: list[str] = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "STREET",
    "CITY",
    "FI_POSTAL_CODE",
    "IP_ADDRESS",
    "CREDIT_CARD",
    "IBAN_CODE",
    "FI_HETU",
]

# extract: no redaction (entity list unused)
EXTRACT_ENTITIES: list[str] = []

# Back-compat alias used across the codebase
DEFAULT_ENTITIES: list[str] = list(STRICT_ENTITIES)

VALID_MODES: tuple[str, ...] = ("extract", "standard", "strict")

# Optional aliases accepted on CLI / YAML
_MODE_ALIASES: dict[str, str] = {
    "extract": "extract",
    "text": "extract",
    "plain": "extract",
    "standard": "standard",
    "normal": "standard",
    "pii": "standard",
    "strict": "strict",
    "full": "strict",
}

MODE_ENTITY_PRESETS: dict[str, list[str]] = {
    "extract": list(EXTRACT_ENTITIES),
    "standard": list(STANDARD_ENTITIES),
    "strict": list(STRICT_ENTITIES),
}

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


# Field labels only (not company/person names). Users extend via config.
DEFAULT_ALLOWLIST: list[str] = [
    "Y-tunnus",
    "Y tunnus",
    "Hetu",
    "Henkilötunnus",
    "ALV-numero",
    "ALV numero",
    "ALV",
    "VAT",
    "IBAN",
    "Email",
    "Phone",
]


def normalize_mode(mode: str | None) -> str:
    """Map user mode string to a canonical mode name."""
    if not mode:
        return "strict"
    key = mode.strip().casefold()
    if key not in _MODE_ALIASES:
        raise ValueError(
            f"Unknown mode {mode!r}. Expected one of: "
            f"{', '.join(VALID_MODES)} "
            f"(aliases: text/plain→extract, normal/pii→standard, full→strict)."
        )
    return _MODE_ALIASES[key]


def entities_for_mode(mode: str) -> list[str]:
    """Return a copy of the entity list for a canonical mode."""
    canonical = normalize_mode(mode)
    return list(MODE_ENTITY_PRESETS[canonical])


@dataclass
class AnonymizerConfig:
    score_threshold: float = 0.5
    # Operating mode: extract | standard | strict (default strict)
    mode: str = "strict"
    entities: list[str] = field(default_factory=lambda: list(STRICT_ENTITIES))
    # True when YAML or CLI set an explicit entity list (overrides mode preset)
    entities_explicit: bool = False
    allowlist: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWLIST))
    denylist: list[DenylistEntry] = field(default_factory=list)
    lang: str = "auto"
    include_dates: bool = False
    # Optional LLM layer (off by default)
    use_llm: bool = False
    # Default local; remote requires explicit provider "xai"
    llm_provider: str = "ollama"  # ollama | xai | off
    llm_model: str | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    # Keep PDF running headers/footers/page marks (default: strip them)
    keep_headers: bool = False

    def apply_mode(self, mode: str | None = None) -> None:
        """Set mode and refresh entities unless user overrode the entity list."""
        if mode is not None:
            self.mode = normalize_mode(mode)
        else:
            self.mode = normalize_mode(self.mode)
        if not self.entities_explicit:
            self.entities = entities_for_mode(self.mode)

    def effective_entities(self) -> list[str]:
        if self.mode == "extract":
            return []
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
    if "mode" in data and data["mode"]:
        cfg.mode = normalize_mode(str(data["mode"]))
    if "entities" in data and data["entities"] is not None:
        cfg.entities = list(data["entities"])
        cfg.entities_explicit = True
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
    if "use_llm" in data:
        cfg.use_llm = bool(data["use_llm"])
    if "llm_provider" in data and data["llm_provider"]:
        cfg.llm_provider = str(data["llm_provider"])
    if "llm_model" in data:
        cfg.llm_model = str(data["llm_model"]) if data["llm_model"] else None
    if "ollama_url" in data and data["ollama_url"]:
        cfg.ollama_url = str(data["ollama_url"])
    if "keep_headers" in data:
        cfg.keep_headers = bool(data["keep_headers"])
    # Apply mode preset when entities were not explicitly listed
    if not cfg.entities_explicit:
        cfg.entities = entities_for_mode(cfg.mode)
    return cfg
