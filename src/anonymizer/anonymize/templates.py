"""Named allow/deny templates (use-case packs).

Templates are the user-facing list model. At runtime they merge into
``AnonymizerConfig.allowlist`` / ``denylist``. Builtins ship with the package;
user packs live under ``~/.config/anonymizer/templates/``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from anonymizer.anonymize.config import AnonymizerConfig, DenylistEntry

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def user_templates_dir() -> Path:
    override = os.environ.get("ANONYMIZER_TEMPLATES")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "anonymizer" / "templates"
    return Path.home() / ".config" / "anonymizer" / "templates"


def builtin_templates_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates" / "builtin"


def slugify(name: str) -> str:
    s = name.strip().casefold()
    s = _SLUG_RE.sub("-", s).strip("-")
    return s or "template"


@dataclass
class Template:
    """One allow/deny pack."""

    id: str
    title: str = ""
    description: str = ""
    allow: list[str] = field(default_factory=list)
    deny: list[DenylistEntry] = field(default_factory=list)
    builtin: bool = False
    default: bool = False  # selected for new users / default enable
    path: Path | None = None
    languages: list[str] = field(default_factory=list)

    def display_title(self) -> str:
        return self.title or self.id


@dataclass
class MergedLists:
    allow: list[str]
    deny: list[DenylistEntry]
    template_ids: list[str]
    # Surfaces that appeared in both allow and deny (allow kept)
    conflicts: list[str] = field(default_factory=list)


def _parse_deny_items(raw: object) -> list[DenylistEntry]:
    out: list[DenylistEntry] = []
    if not raw:
        return out
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            t = item.strip()
            if t:
                out.append(DenylistEntry(text=t, entity_type="ORG"))
        elif isinstance(item, dict):
            t = str(item.get("text", "")).strip()
            if t:
                out.append(
                    DenylistEntry(
                        text=t,
                        entity_type=str(item.get("entity_type", "ORG") or "ORG"),
                    )
                )
    return out


def load_template_file(path: Path, *, builtin: bool = False) -> Template:
    path = path.expanduser()
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"Template {path} must be a YAML mapping")
    tid = str(data.get("id") or path.stem).strip()
    if not tid:
        tid = path.stem
    allow_raw = data.get("allow") or []
    if not isinstance(allow_raw, list):
        raise ValueError(f"Template {path}: allow must be a list")
    allow = [str(x).strip() for x in allow_raw if str(x).strip()]
    deny = _parse_deny_items(data.get("deny"))
    langs = data.get("languages") or data.get("lang") or []
    if isinstance(langs, str):
        languages = [langs]
    elif isinstance(langs, list):
        languages = [str(x) for x in langs]
    else:
        languages = []
    return Template(
        id=tid,
        title=str(data.get("title") or data.get("name") or tid),
        description=str(data.get("description") or ""),
        allow=allow,
        deny=deny,
        builtin=bool(data.get("builtin", builtin)),
        default=bool(data.get("default", False)),
        path=path,
        languages=languages,
    )


def discover_templates(
    *,
    extra_dirs: Iterable[Path] | None = None,
    include_builtin: bool = True,
    include_user: bool = True,
) -> list[Template]:
    """Load all templates. User packs override builtin ids of the same name."""
    by_id: dict[str, Template] = {}
    dirs: list[tuple[Path, bool]] = []
    if include_builtin:
        dirs.append((builtin_templates_dir(), True))
    if include_user:
        dirs.append((user_templates_dir(), False))
    if extra_dirs:
        for d in extra_dirs:
            dirs.append((Path(d).expanduser(), False))

    for directory, is_builtin in dirs:
        if not directory.is_dir():
            continue
        paths = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
        for path in paths:
            try:
                tmpl = load_template_file(path, builtin=is_builtin)
            except (OSError, ValueError, yaml.YAMLError):
                continue
            # User packs override builtins with the same id
            if tmpl.id in by_id and is_builtin and not by_id[tmpl.id].builtin:
                continue
            by_id[tmpl.id] = tmpl

    return sorted(by_id.values(), key=lambda t: (not t.builtin, t.id))


def default_enabled_ids(templates: list[Template] | None = None) -> list[str]:
    packs = templates if templates is not None else discover_templates()
    return [t.id for t in packs if t.default]


def resolve_enabled_ids(
    *,
    cli_templates: str | list[str] | None = None,
    config_templates: list[str] | None = None,
    all_templates: list[Template] | None = None,
) -> list[str]:
    """CLI overrides config; config overrides builtin defaults."""
    packs = all_templates if all_templates is not None else discover_templates()
    known = {t.id for t in packs}
    if cli_templates is not None:
        if isinstance(cli_templates, str):
            raw = [p.strip() for p in cli_templates.split(",") if p.strip()]
        else:
            raw = [str(p).strip() for p in cli_templates if str(p).strip()]
        # Empty CLI string means explicitly none
        return [i for i in raw if i in known]
    if config_templates is not None:
        return [i for i in config_templates if i in known]
    return default_enabled_ids(packs)


def union_templates(
    templates: list[Template],
    enabled_ids: Iterable[str],
) -> MergedLists:
    """Union selected packs. Allow wins over deny on conflict."""
    by_id = {t.id: t for t in templates}
    allow: list[str] = []
    allow_seen: set[str] = set()
    deny_map: dict[str, DenylistEntry] = {}  # casefold -> entry
    used: list[str] = []

    for tid in enabled_ids:
        t = by_id.get(tid)
        if t is None:
            continue
        used.append(tid)
        for a in t.allow:
            key = a.casefold()
            if key not in allow_seen:
                allow.append(a)
                allow_seen.add(key)
        for d in t.deny:
            key = d.text.casefold()
            if key not in deny_map:
                deny_map[key] = d

    conflicts: list[str] = []
    for key in list(deny_map.keys()):
        if key in allow_seen:
            conflicts.append(deny_map[key].text)
            del deny_map[key]

    return MergedLists(
        allow=allow,
        deny=list(deny_map.values()),
        template_ids=used,
        conflicts=conflicts,
    )


def apply_templates_to_config(
    cfg: AnonymizerConfig,
    *,
    enabled_ids: list[str] | None = None,
    extra_dirs: Iterable[Path] | None = None,
    replace_lists: bool = True,
) -> MergedLists:
    """Merge templates into config allow/deny.

    When *replace_lists* is True (default), template union becomes the allowlist
    and is prepended/merged into denylist (existing denylist entries kept if
    not conflicting with allow). ``allowlist_extra`` is still appended after.
    """
    packs = discover_templates(extra_dirs=extra_dirs)
    if enabled_ids is None:
        enabled_ids = default_enabled_ids(packs)
    merged = union_templates(packs, enabled_ids)

    if replace_lists:
        cfg.allowlist = list(merged.allow)
        # Start denylist from templates; keep any pre-existing that aren't allowed
        existing = list(cfg.denylist)
        cfg.denylist = list(merged.deny)
        allow_cf = {a.casefold() for a in cfg.allowlist}
        seen_deny = {d.text.casefold() for d in cfg.denylist}
        for e in existing:
            k = e.text.casefold()
            if k in allow_cf or k in seen_deny:
                continue
            cfg.denylist.append(e)
            seen_deny.add(k)
    else:
        # Append-only mode (legacy hybrid)
        allow_cf = {a.casefold() for a in cfg.allowlist}
        for a in merged.allow:
            if a.casefold() not in allow_cf:
                cfg.allowlist.append(a)
                allow_cf.add(a.casefold())
        seen_deny = {d.text.casefold() for d in cfg.denylist}
        for d in merged.deny:
            if d.text.casefold() in allow_cf or d.text.casefold() in seen_deny:
                continue
            cfg.denylist.append(d)
            seen_deny.add(d.text.casefold())

    # allowlist_extra still wins as append
    if cfg.allowlist_extra:
        seen = {a.casefold() for a in cfg.allowlist}
        for item in cfg.allowlist_extra:
            if item and item.casefold() not in seen:
                cfg.allowlist.append(item)
                seen.add(item.casefold())
        # strip deny that collides with extras
        cfg.denylist = [
            d for d in cfg.denylist if d.text.casefold() not in seen
        ]

    return merged


def template_to_yaml_dict(t: Template) -> dict:
    return {
        "id": t.id,
        "title": t.title or t.id,
        "description": t.description or "",
        "builtin": False,
        "default": False,
        "languages": list(t.languages),
        "allow": list(t.allow),
        "deny": [
            {"text": d.text, "entity_type": d.entity_type} for d in t.deny
        ],
    }


def save_template(t: Template, path: Path | None = None) -> Path:
    """Write a user template (never marks builtin). Returns path."""
    if path is None:
        dest_dir = user_templates_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{slugify(t.id)}.yaml"
    else:
        path = path.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
    payload = template_to_yaml_dict(t)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def merge_into_template(
    t: Template,
    *,
    allow_add: Iterable[str] = (),
    deny_add: Iterable[DenylistEntry | str] = (),
) -> Template:
    """Return a copy of *t* with new surfaces (casefold-unique)."""
    allow = list(t.allow)
    seen_a = {a.casefold() for a in allow}
    for a in allow_add:
        s = str(a).strip()
        if s and s.casefold() not in seen_a:
            allow.append(s)
            seen_a.add(s.casefold())
    deny = list(t.deny)
    seen_d = {d.text.casefold() for d in deny}
    for d in deny_add:
        if isinstance(d, str):
            entry = DenylistEntry(text=d.strip(), entity_type="ORG")
        else:
            entry = d
        if not entry.text or entry.text.casefold() in seen_d:
            continue
        if entry.text.casefold() in seen_a:
            continue  # allow wins
        deny.append(entry)
        seen_d.add(entry.text.casefold())
    return Template(
        id=t.id,
        title=t.title,
        description=t.description,
        allow=allow,
        deny=deny,
        builtin=False,
        default=t.default,
        path=t.path,
        languages=list(t.languages),
    )


def session_to_teach_lists(session: object) -> tuple[list[str], list[DenylistEntry]]:
    """Extract keep-clear surfaces and user-added denials from a ReviewSession."""
    # Lazy typing to avoid circular imports at module load in some paths
    from anonymizer.anonymize.review import ReviewSession

    if not isinstance(session, ReviewSession):
        raise TypeError("session must be a ReviewSession")
    allow: list[str] = []
    deny: list[DenylistEntry] = []
    for f in session.findings:
        surface = (f.original or "").strip()
        if not surface:
            continue
        if not f.enabled:
            allow.append(surface)
        elif f.source == "user":
            deny.append(
                DenylistEntry(
                    text=surface,
                    entity_type=f.entity_type or "ORG",
                )
            )
    return allow, deny


def teach_template(
    template_id: str,
    session: object,
    *,
    create_title: str | None = None,
) -> Path:
    """Merge review decisions into a user template; fork if target is builtin."""
    packs = discover_templates()
    by_id = {t.id: t for t in packs}
    allow_add, deny_add = session_to_teach_lists(session)

    existing = by_id.get(template_id)
    if existing is None:
        base = Template(
            id=slugify(template_id),
            title=create_title or template_id,
            description="User template (taught from review)",
            builtin=False,
            default=False,
        )
    elif existing.builtin:
        # Fork — never overwrite shipped packs
        base = Template(
            id=slugify(f"{existing.id}-custom"),
            title=f"{existing.display_title()} (my copy)",
            description=f"Fork of builtin {existing.id}",
            allow=list(existing.allow),
            deny=list(existing.deny),
            builtin=False,
            default=False,
            languages=list(existing.languages),
        )
    else:
        base = existing

    updated = merge_into_template(base, allow_add=allow_add, deny_add=deny_add)
    return save_template(updated)


def maybe_migrate_config_lists(config_path: Path | None) -> Path | None:
    """If config has allow/deny and no templates yet, write migrated user template.

    Returns path written, or None if nothing to do.
    """
    if config_path is None or not config_path.is_file():
        return None
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("templates_enabled") is not None or raw.get("templates") is not None:
        return None
    has_lists = bool(raw.get("allowlist") is not None or raw.get("denylist"))
    if not has_lists:
        return None
    # Already migrated?
    marker = user_templates_dir() / "migrated-from-config.yaml"
    if marker.is_file():
        return None

    allow_raw = raw.get("allowlist") or []
    allow = [str(x).strip() for x in allow_raw if str(x).strip()] if isinstance(allow_raw, list) else []
    deny = _parse_deny_items(raw.get("denylist"))
    # Also fold allowlist_extra
    extra = raw.get("allowlist_extra") or []
    if isinstance(extra, list):
        seen = {a.casefold() for a in allow}
        for x in extra:
            s = str(x).strip()
            if s and s.casefold() not in seen:
                allow.append(s)
                seen.add(s.casefold())

    if not allow and not deny:
        return None

    t = Template(
        id="migrated-from-config",
        title="Migrated from config",
        description="Auto-created from previous allowlist/denylist in config.yaml",
        allow=allow,
        deny=deny,
        builtin=False,
        default=True,
    )
    path = save_template(t, marker)
    # Enable in config
    raw["templates_enabled"] = ["migrated-from-config"] + default_enabled_ids()
    # Keep old keys for one release but prefer templates
    try:
        config_path.write_text(
            yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    except OSError:
        pass
    return path
