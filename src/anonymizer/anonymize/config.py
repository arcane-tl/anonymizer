"""Configuration defaults, mode presets, and YAML loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from anonymizer.anonymize.domain_lexicon import DEFAULT_ALLOWLIST_SEEDS

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

# How to replace detected spans in the output body
VALID_REDACT_STYLES: tuple[str, ...] = ("placeholder", "remove")
_REDACT_STYLE_ALIASES: dict[str, str] = {
    "placeholder": "placeholder",
    "placeholders": "placeholder",
    "tags": "placeholder",
    "tag": "placeholder",
    "remove": "remove",
    "delete": "remove",
    "empty": "remove",
    "strip": "remove",
}

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


# Field labels + contract roles + legal collocations (not company catalogs).
# Users append via allowlist_extra; allowlist: still replaces defaults.
DEFAULT_ALLOWLIST: list[str] = list(DEFAULT_ALLOWLIST_SEEDS)


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


def normalize_redact_style(style: str | None) -> str:
    """Map user redaction style to placeholder | remove."""
    if not style:
        return "placeholder"
    key = style.strip().casefold()
    if key not in _REDACT_STYLE_ALIASES:
        raise ValueError(
            f"Unknown redact style {style!r}. Expected one of: "
            f"{', '.join(VALID_REDACT_STYLES)} "
            f"(aliases: tags→placeholder, delete/empty/strip→remove)."
        )
    return _REDACT_STYLE_ALIASES[key]


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
    # Appended after allowlist load (does not replace defaults)
    allowlist_extra: list[str] = field(default_factory=list)
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
    # placeholder = [PERSON_1] tags (default); remove = delete the span
    redact_style: str = "placeholder"
    # Output: md (default) | source (native PDF/DOCX) | both
    output_format: str = "md"

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


class ConfigError(ValueError):
    """User-facing failure loading or interpreting a YAML config file."""


def _format_yaml_error(path: Path, exc: yaml.YAMLError) -> str:
    """Build a short, actionable message from a PyYAML exception."""
    mark = getattr(exc, "problem_mark", None)
    where = ""
    if mark is not None:
        # problem_mark is 0-based
        where = f" at line {mark.line + 1}, column {mark.column + 1}"
    problem = getattr(exc, "problem", None)
    if problem:
        detail = str(problem).strip().rstrip(".")
    else:
        detail = str(exc).strip().splitlines()[0]
    return (
        f"Invalid YAML in config file {path}{where}: {detail}. "
        f"Check indentation and quotes (see config.example.yaml)."
    )


def load_config(path: Path | None) -> AnonymizerConfig:
    cfg = AnonymizerConfig()
    if path is None:
        return cfg
    path = path.expanduser()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {path}: {exc}") from exc

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(_format_yaml_error(path, exc)) from exc

    if raw is None:
        data: dict[str, Any] = {}
    elif not isinstance(raw, dict):
        raise ConfigError(
            f"Config file {path} must be a YAML mapping (key: value pairs), "
            f"not a {type(raw).__name__}. See config.example.yaml."
        )
    else:
        data = raw

    try:
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
        if "allowlist_extra" in data and data["allowlist_extra"] is not None:
            cfg.allowlist_extra = [str(x) for x in data["allowlist_extra"]]
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
        if "redact_style" in data and data["redact_style"]:
            cfg.redact_style = normalize_redact_style(str(data["redact_style"]))
        if "format" in data and data["format"]:
            # Lazy import avoids circular import with output package at module load
            from anonymizer.output.native import normalize_output_format

            cfg.output_format = normalize_output_format(str(data["format"]))
        if "output_format" in data and data["output_format"]:
            from anonymizer.output.native import normalize_output_format

            cfg.output_format = normalize_output_format(str(data["output_format"]))
    except ConfigError:
        raise
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid config in {path}: {exc}") from exc

    # Apply mode preset when entities were not explicitly listed
    if not cfg.entities_explicit:
        cfg.entities = entities_for_mode(cfg.mode)
    # Normalize style even if default
    cfg.redact_style = normalize_redact_style(cfg.redact_style)
    from anonymizer.output.native import normalize_output_format

    cfg.output_format = normalize_output_format(cfg.output_format)
    # Append extras without replacing the base list
    if cfg.allowlist_extra:
        seen = {a.casefold() for a in cfg.allowlist}
        for item in cfg.allowlist_extra:
            if item and item.casefold() not in seen:
                cfg.allowlist.append(item)
                seen.add(item.casefold())
    return cfg
