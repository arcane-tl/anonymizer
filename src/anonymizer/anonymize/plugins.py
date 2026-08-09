"""Load custom recognizers from local YAML or Python modules (config-driven).

Security: only paths/modules explicitly listed in config; no network fetch,
no automatic scanning of site-packages.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from presidio_analyzer import EntityRecognizer

from anonymizer.anonymize.entity_types import EntityTypeRegistry, EntityTypeSpec
from anonymizer.anonymize.recognizers.pattern_list import PatternListRecognizer, PatternSpec

logger = logging.getLogger(__name__)


@dataclass
class PluginLoadResult:
    recognizers: list[EntityRecognizer] = field(default_factory=list)
    # (entity_code, label, priority, modes)
    entity_specs: list[EntityTypeSpec] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _as_mapping(entry: Any) -> dict[str, Any]:
    if isinstance(entry, str):
        # Shorthand: path to YAML
        return {"path": entry}
    if isinstance(entry, dict):
        return entry
    raise TypeError(f"recognizer entry must be a path string or mapping, got {type(entry).__name__}")


def _resolve_path(raw: str, *, base_dir: Path | None) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute() and base_dir is not None:
        p = (base_dir / p).resolve()
    else:
        p = p.resolve()
    return p


def load_yaml_pattern_recognizer(
    path: Path,
    *,
    registry: EntityTypeRegistry | None = None,
) -> tuple[PatternListRecognizer, EntityTypeSpec]:
    """Load a PatternListRecognizer from a YAML file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read recognizer YAML {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Recognizer YAML {path} must be a mapping")

    name = str(raw.get("name") or path.stem)
    entity_type = str(raw.get("entity_type") or "").strip().upper()
    if not entity_type:
        raise ValueError(f"Recognizer YAML {path} missing entity_type")
    label = str(raw.get("label") or entity_type).strip().upper()
    priority = int(raw.get("priority", 3))
    modes_raw = raw.get("modes") or ["strict", "standard"]
    modes = frozenset(str(m).lower() for m in modes_raw)

    patterns_raw = raw.get("patterns")
    if not patterns_raw or not isinstance(patterns_raw, list):
        raise ValueError(f"Recognizer YAML {path} needs a non-empty patterns: list")

    patterns: list[PatternSpec] = []
    for i, item in enumerate(patterns_raw):
        if not isinstance(item, dict):
            raise ValueError(f"{path} patterns[{i}] must be a mapping")
        regex = item.get("regex")
        if not regex:
            raise ValueError(f"{path} patterns[{i}] missing regex")
        patterns.append(
            PatternSpec(
                name=str(item.get("name") or f"p{i}"),
                regex=str(regex),
                score=float(item.get("score", 0.85)),
            )
        )

    rec = PatternListRecognizer(name=name, entity_type=entity_type, patterns=patterns)
    rec.supported_language = "en"
    spec = EntityTypeSpec(
        code=entity_type,
        label=label,
        priority=priority,
        modes=modes,
    )
    if registry is not None:
        registry.register(spec)
    return rec, spec


def load_python_recognizer(
    *,
    module: str | None = None,
    python_path: Path | None = None,
    class_name: str | None = None,
) -> EntityRecognizer:
    """Import an EntityRecognizer subclass from a module or .py file."""
    if module:
        # "pkg.mod:ClassName" or "pkg.mod" + class_name
        mod_name, _, cls_part = module.partition(":")
        cls_name = class_name or cls_part
        if not cls_name:
            raise ValueError(
                f"module {module!r} must be 'package.module:ClassName' or set class:"
            )
        mod = importlib.import_module(mod_name)
        cls = getattr(mod, cls_name, None)
    elif python_path is not None:
        if not class_name:
            raise ValueError(f"python plugin {python_path} requires class: ClassName")
        spec = importlib.util.spec_from_file_location(
            f"anonymizer_plugin_{python_path.stem}", python_path
        )
        if spec is None or spec.loader is None:
            raise ValueError(f"Cannot load Python plugin from {python_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cls = getattr(mod, class_name, None)
    else:
        raise ValueError("Python plugin needs module: or python: path")

    if cls is None:
        raise ValueError("Plugin class not found")
    if not isinstance(cls, type):
        raise ValueError(f"Plugin {cls!r} is not a class")
    inst = cls()
    if not isinstance(inst, EntityRecognizer):
        raise TypeError(
            f"Plugin {cls.__name__} must subclass presidio_analyzer.EntityRecognizer"
        )
    inst.supported_language = getattr(inst, "supported_language", None) or "en"
    return inst


def load_recognizer_plugins(
    entries: list[Any] | None,
    *,
    base_dir: Path | None = None,
    registry: EntityTypeRegistry | None = None,
) -> PluginLoadResult:
    """Load all config ``recognizers:`` entries."""
    out = PluginLoadResult()
    if not entries:
        return out

    for i, raw in enumerate(entries):
        try:
            entry = _as_mapping(raw)
        except TypeError as exc:
            out.errors.append(f"recognizers[{i}]: {exc}")
            continue

        try:
            if "path" in entry or (
                len(entry) == 1 and next(iter(entry)).endswith((".yaml", ".yml"))
            ):
                path_raw = entry.get("path") or next(iter(entry))
                path = _resolve_path(str(path_raw), base_dir=base_dir)
                if not path.is_file():
                    raise ValueError(f"Recognizer file not found: {path}")
                if path.suffix.lower() not in {".yaml", ".yml"}:
                    raise ValueError(f"path: expects .yaml/.yml, got {path}")
                rec, spec = load_yaml_pattern_recognizer(path, registry=registry)
                out.recognizers.append(rec)
                out.entity_specs.append(spec)
                continue

            if "module" in entry:
                rec = load_python_recognizer(
                    module=str(entry["module"]),
                    class_name=str(entry["class"]) if entry.get("class") else None,
                )
                out.recognizers.append(rec)
                for ent in rec.supported_entities or []:
                    label = str(entry.get("label") or ent)
                    priority = int(entry.get("priority", 3))
                    modes = entry.get("modes") or ["strict", "standard"]
                    spec = EntityTypeSpec(
                        code=str(ent).upper(),
                        label=label.upper(),
                        priority=priority,
                        modes=frozenset(str(m).lower() for m in modes),
                    )
                    if registry is not None:
                        registry.register(spec)
                    out.entity_specs.append(spec)
                continue

            if "python" in entry:
                py_path = _resolve_path(str(entry["python"]), base_dir=base_dir)
                if not py_path.is_file():
                    raise ValueError(f"Python plugin not found: {py_path}")
                rec = load_python_recognizer(
                    python_path=py_path,
                    class_name=str(entry.get("class") or ""),
                )
                out.recognizers.append(rec)
                for ent in rec.supported_entities or []:
                    label = str(entry.get("label") or ent)
                    priority = int(entry.get("priority", 3))
                    modes = entry.get("modes") or ["strict", "standard"]
                    spec = EntityTypeSpec(
                        code=str(ent).upper(),
                        label=label.upper(),
                        priority=priority,
                        modes=frozenset(str(m).lower() for m in modes),
                    )
                    if registry is not None:
                        registry.register(spec)
                    out.entity_specs.append(spec)
                continue

            out.errors.append(
                f"recognizers[{i}]: need path: (YAML), module:, or python: + class:"
            )
        except Exception as exc:  # noqa: BLE001 — collect for config load
            out.errors.append(f"recognizers[{i}]: {exc}")
            logger.warning("Failed to load recognizer plugin: %s", exc)

    return out
