"""Debug provenance: source chips + per-run JSON logs (opt-in)."""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from anonymizer.models import AnonymizeResult, EntityHit

_SOURCE_FAMILY_LABELS = {
    "spacy": "spaCy",
    "pattern": "pattern",
    "denylist": "deny",
    "org_stem": "stem",
    "llm": "LLM",
    "user": "added",
}


def debug_enabled(
    *,
    flag: bool | None = None,
    config_debug: bool = False,
) -> bool:
    """True if CLI/GUI/config/env asked for debug provenance."""
    if flag is True:
        return True
    if config_debug:
        return True
    env = (os.environ.get("ANONYMIZER_DEBUG") or "").strip().casefold()
    return env in {"1", "true", "yes", "on"}


def format_sources_chip(sources: Iterable[str] | None) -> str:
    """Short UI chip: ``spaCy · pattern`` (empty if no sources)."""
    if not sources:
        return ""
    seen: list[str] = []
    for raw in sources:
        if not raw:
            continue
        family = str(raw).split(":", 1)[0].casefold()
        label = _SOURCE_FAMILY_LABELS.get(family, family)
        if label not in seen:
            seen.append(label)
    return " · ".join(seen)


def default_debug_log_dir() -> Path:
    return Path.home() / ".local" / "state" / "anonymizer" / "logs"


def _safe_stem(name: str) -> str:
    stem = Path(name).stem or "doc"
    stem = re.sub(r"[^\w.\-]+", "_", stem, flags=re.UNICODE)
    return stem[:80] or "doc"


def resolve_debug_log_path(source_file: str | Path | None = None) -> Path:
    """Return path for this run's debug JSON.

    ``ANONYMIZER_DEBUG_LOG`` may be a file path or a directory.
    """
    env = (os.environ.get("ANONYMIZER_DEBUG_LOG") or "").strip()
    ts = time.strftime("%Y%m%d-%H%M%S")
    stem = _safe_stem(str(source_file or "doc"))
    default_name = f"run-{ts}-{stem}.json"
    if not env:
        return default_debug_log_dir() / default_name
    p = Path(env).expanduser()
    if p.exists() and p.is_dir():
        return p / default_name
    if str(env).endswith(("/", os.sep)) or (not p.suffix and not p.exists()):
        # treat as directory intent
        return p / default_name
    return p


def _source_family(src: str) -> str:
    if not src:
        return "unknown"
    return src.split(":", 1)[0].casefold() or "unknown"


def build_run_debug_payload(
    result: AnonymizeResult,
    *,
    source_file: str | Path | None = None,
    version: str = "",
) -> dict[str, Any]:
    """Build summary + findings list (includes PII surfaces)."""
    by_type: Counter[str] = Counter()
    by_family: Counter[str] = Counter()
    findings: list[dict[str, Any]] = []

    # Index hit_meta by placeholder when available
    meta = dict(getattr(result, "hit_meta", None) or {})

    # Auto mapping findings
    for ph, surface in (result.mapping or {}).items():
        m = meta.get(ph) or {}
        sources = list(m.get("sources") or [])
        if not sources and m.get("source"):
            sources = [str(m["source"])]
        if not sources:
            # fall back to first matching hit
            for h in result.hits or []:
                if h.text == surface or (
                    h.entity_type
                    and ph.startswith(f"[{h.entity_type}_")
                ):
                    if h.source:
                        sources = [h.source]
                    break
        et = str(m.get("entity_type") or ph.strip("[]").rsplit("_", 1)[0])
        by_type[et] += 1
        if sources:
            for s in sources:
                by_family[_source_family(str(s))] += 1
        else:
            by_family["unknown"] += 1
        score = None
        for h in result.hits or []:
            if h.text == surface:
                score = h.score
                break
        findings.append(
            {
                "placeholder": ph,
                "entity_type": et,
                "surface": surface,
                "sources": sources,
                "proposal": False,
                "score": score,
            }
        )

    prop_by_type: Counter[str] = Counter()
    for ph, surface in (getattr(result, "proposals", None) or {}).items():
        m = meta.get(ph) or {}
        sources = list(m.get("sources") or [])
        if not sources and m.get("source"):
            sources = [str(m["source"])]
        et = str(m.get("entity_type") or ph.strip("[]").rsplit("_", 1)[0])
        prop_by_type[et] += 1
        findings.append(
            {
                "placeholder": ph,
                "entity_type": et,
                "surface": surface,
                "sources": sources,
                "proposal": True,
                "score": None,
            }
        )

    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": version,
        "source_file": str(source_file) if source_file else "",
        "mode": getattr(result, "mode", ""),
        "lang": {
            "passes": list(result.language.nlp_passes),
            "detected": list(result.language.detected),
            "reason": result.language.reason,
        },
        "debug": True,
        "summary": {
            "auto_redactions": len(result.mapping or {}),
            "proposals": len(getattr(result, "proposals", None) or {}),
            "by_entity_type": dict(by_type.most_common()),
            "by_source_family": dict(by_family.most_common()),
            "proposals_by_type": dict(prop_by_type.most_common()),
        },
        "findings": findings,
    }


def write_run_debug_log(
    result: AnonymizeResult,
    *,
    source_file: str | Path | None = None,
    version: str = "",
    path: Path | None = None,
) -> Path | None:
    """Write debug JSON (mode 0600). Returns path or None on failure."""
    dest = path or resolve_debug_log_path(source_file)
    payload = build_run_debug_payload(
        result, source_file=source_file, version=version
    )
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            dest.chmod(0o600)
        except OSError:
            pass
        return dest
    except OSError:
        return None


def sources_for_placeholder(
    ph: str,
    hit_meta: dict[str, dict[str, Any]] | None,
    hits: list[EntityHit] | None = None,
    surface: str | None = None,
) -> list[str]:
    """Resolve detector sources for a Review placeholder."""
    m = (hit_meta or {}).get(ph) or {}
    sources = list(m.get("sources") or [])
    if not sources and m.get("source"):
        sources = [str(m["source"])]
    if sources:
        return sources
    if hits and surface is not None:
        for h in hits:
            if h.text == surface and h.source:
                return [h.source]
    return []
