"""Central entity-type registry for placeholders, modes, and merge priority.

Built-in types match historical STRICT/STANDARD presets. Custom YAML/Python
plugins register additional types on a config-scoped :class:`EntityTypeRegistry`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class EntityTypeSpec:
    """One entity type known to the pipeline."""

    code: str
    label: str
    priority: int = 2
    # Which mode presets include this type by default
    modes: frozenset[str] = field(default_factory=lambda: frozenset({"strict"}))


def _spec(
    code: str,
    label: str | None = None,
    *,
    priority: int = 2,
    modes: Iterable[str] = ("strict",),
) -> EntityTypeSpec:
    return EntityTypeSpec(
        code=code.upper(),
        label=(label or code).upper(),
        priority=priority,
        modes=frozenset(m.lower() for m in modes),
    )


# Built-in catalogue (mirrors config STRICT/STANDARD + mapping TYPE_LABELS)
_BUILTIN_SPECS: tuple[EntityTypeSpec, ...] = (
    _spec("PERSON", priority=2, modes=("strict", "standard")),
    _spec("ORG", priority=2, modes=("strict",)),
    _spec("ORGANIZATION", "ORG", priority=2, modes=("strict",)),
    _spec("EMAIL_ADDRESS", "EMAIL", priority=3, modes=("strict", "standard")),
    _spec("PHONE_NUMBER", "PHONE", priority=3, modes=("strict", "standard")),
    _spec("LOCATION", priority=1, modes=("strict",)),
    _spec("LOC", "LOCATION", priority=1, modes=("strict",)),
    _spec("GPE", "LOCATION", priority=1, modes=("strict",)),
    _spec("STREET", priority=3, modes=("strict", "standard")),
    _spec("CITY", priority=3, modes=("strict", "standard")),
    # Optional via include_dates / --entities (not in default mode presets)
    _spec("DATE_TIME", "DATE", priority=2, modes=()),
    _spec("IP_ADDRESS", "IP", priority=3, modes=("strict", "standard")),
    _spec("CREDIT_CARD", priority=3, modes=("strict", "standard")),
    _spec("IBAN_CODE", "IBAN", priority=3, modes=("strict", "standard")),
    # Known aliases / rare Presidio types — label only, not mode presets
    _spec("US_SSN", priority=3, modes=()),
    _spec("US_DRIVER_LICENSE", "US_DL", priority=3, modes=()),
    _spec("NRP", priority=1, modes=()),
    _spec("FI_HETU", priority=3, modes=("strict", "standard")),
    _spec("FI_BUSINESS_ID", priority=3, modes=("strict",)),
    _spec("FI_VAT", "VAT_FI", priority=3, modes=("strict",)),
    _spec("FI_LICENSE_PLATE", "PLATE_FI", priority=3, modes=("strict",)),
    _spec("FI_POSTAL_CODE", "POSTAL", priority=3, modes=("strict", "standard")),
    _spec("VEHICLE_VIN", "VIN", priority=3, modes=("strict",)),
    _spec("URL", priority=3, modes=("strict",)),
    _spec("CUSTOM", priority=2, modes=()),
)


@dataclass
class EntityTypeRegistry:
    """Mutable registry: built-ins plus plugin-registered types."""

    _by_code: dict[str, EntityTypeSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self._by_code:
            for s in _BUILTIN_SPECS:
                self._by_code[s.code] = s

    @classmethod
    def builtins(cls) -> EntityTypeRegistry:
        return cls()

    def get(self, code: str) -> EntityTypeSpec | None:
        return self._by_code.get(code.upper())

    def register(self, spec: EntityTypeSpec, *, overwrite: bool = False) -> None:
        key = spec.code.upper()
        if key in self._by_code and not overwrite:
            existing = self._by_code[key]
            # Allow identical re-register; reject conflicting label/priority
            if existing.label != spec.label or existing.priority != spec.priority:
                raise ValueError(
                    f"Entity type {key!r} already registered as "
                    f"label={existing.label!r} priority={existing.priority}; "
                    f"got label={spec.label!r} priority={spec.priority}"
                )
            return
        self._by_code[key] = EntityTypeSpec(
            code=key,
            label=spec.label.upper(),
            priority=spec.priority,
            modes=spec.modes or frozenset({"strict"}),
        )

    def register_simple(
        self,
        code: str,
        *,
        label: str | None = None,
        priority: int = 3,
        modes: Iterable[str] = ("strict", "standard"),
    ) -> None:
        self.register(
            EntityTypeSpec(
                code=code.upper(),
                label=(label or code).upper(),
                priority=priority,
                modes=frozenset(m.lower() for m in modes),
            )
        )

    def label_for(self, entity_type: str) -> str:
        key = entity_type.upper()
        spec = self._by_code.get(key)
        if spec:
            return spec.label
        if key.endswith("_LICENSE_PLATE"):
            country = key[: -len("_LICENSE_PLATE")]
            if country:
                return f"PLATE_{country}"
        return key

    def priority_for(self, entity_type: str, default: int = 1) -> int:
        spec = self._by_code.get(entity_type.upper())
        return spec.priority if spec else default

    def codes_for_mode(self, mode: str) -> list[str]:
        """Entity codes included in a mode preset (primary codes only)."""
        m = mode.lower()
        # Prefer canonical codes (skip ORGANIZATION/LOC/GPE aliases for presets)
        skip_aliases = {"ORGANIZATION", "LOC", "GPE"}
        out: list[str] = []
        for code, spec in self._by_code.items():
            if code in skip_aliases:
                continue
            if m in spec.modes:
                out.append(code)
        # Stable order matching historical STRICT list preference
        preferred = [
            "PERSON",
            "ORG",
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "LOCATION",
            "STREET",
            "CITY",
            "URL",
            "IP_ADDRESS",
            "CREDIT_CARD",
            "IBAN_CODE",
            "FI_HETU",
            "FI_BUSINESS_ID",
            "FI_VAT",
            "FI_LICENSE_PLATE",
            "FI_POSTAL_CODE",
            "VEHICLE_VIN",
        ]
        ordered = [c for c in preferred if c in out]
        for c in sorted(out):
            if c not in ordered:
                ordered.append(c)
        return ordered

    def labels_map(self) -> dict[str, str]:
        return {c: s.label for c, s in self._by_code.items()}

    def all_codes(self) -> list[str]:
        return sorted(self._by_code)


def builtin_entity_registry() -> EntityTypeRegistry:
    return EntityTypeRegistry.builtins()
