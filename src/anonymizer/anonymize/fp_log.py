"""Append-only JSONL log of Review keep-clear (false-positive) decisions."""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def default_fp_log_path() -> Path:
    env = (os.environ.get("ANONYMIZER_FP_LOG") or "").strip()
    if env:
        return Path(env).expanduser()
    # XDG-ish local state (macOS/Linux); still fine on Windows via expanduser
    base = Path.home() / ".local" / "state" / "anonymizer"
    return base / "fp-rejects.jsonl"


def append_fp_reject(record: dict[str, Any], path: Path | None = None) -> Path | None:
    """Append one reject record. Returns path written, or None if disabled/fails.

    Set ``ANONYMIZER_FP_LOG=off`` (or ``0`` / ``false``) to disable.
    """
    env = (os.environ.get("ANONYMIZER_FP_LOG") or "").strip().casefold()
    if env in {"off", "0", "false", "no"}:
        return None
    dest = path or default_fp_log_path()
    payload = dict(record)
    payload.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with dest.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        try:
            dest.chmod(0o600)
        except OSError:
            pass
        return dest
    except OSError:
        return None


def log_keep_clear_findings(
    findings: Iterable[Any],
    *,
    lang_passes: list[str] | None = None,
    hit_meta: dict[str, dict[str, Any]] | None = None,
) -> int:
    """Log each keep-clear finding. Returns number of records written."""
    meta = hit_meta or {}
    n = 0
    for f in findings:
        if getattr(f, "enabled", True):
            continue
        ph = getattr(f, "placeholder", "")
        m = meta.get(ph) or {}
        rec = {
            "entity_type": getattr(f, "entity_type", "") or m.get("entity_type", ""),
            "surface": getattr(f, "original", ""),
            "placeholder": ph,
            "sources": list(m.get("sources") or ([m["source"]] if m.get("source") else [])),
            "lang_passes": list(lang_passes or m.get("lang_passes") or []),
            "pos": list(m.get("pos") or []),
            "single_token": bool(m.get("single_token", False)),
            "spacy_label": m.get("spacy_label") or "",
            "finding_source": getattr(f, "source", "auto"),
        }
        if append_fp_reject(rec):
            n += 1
    return n


def load_fp_records(path: Path | None = None) -> list[dict[str, Any]]:
    dest = path or default_fp_log_path()
    if not dest.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        text = dest.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def summarize_fp_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Bucket counts for ``anonymize fp-stats``."""
    by_type: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    single_person = 0
    for r in records:
        et = str(r.get("entity_type") or "?")
        by_type[et] += 1
        sources = r.get("sources") or []
        if isinstance(sources, str):
            sources = [sources]
        if not sources:
            by_source["unknown"] += 1
        else:
            for s in sources:
                tag = str(s).split(":", 1)[0] if s else "unknown"
                by_source[tag] += 1
        if (
            et == "PERSON"
            and r.get("single_token")
            and any(str(s).startswith("spacy:") for s in sources)
        ):
            single_person += 1
    return {
        "total": len(records),
        "by_entity_type": dict(by_type.most_common()),
        "by_source_family": dict(by_source.most_common()),
        "spacy_single_token_person": single_person,
    }
