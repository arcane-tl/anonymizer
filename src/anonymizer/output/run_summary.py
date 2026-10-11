"""Per-run summary for GUI / optional sidecar files (not embedded in Markdown)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anonymizer import __version__


@dataclass
class RunSummary:
    """Compact completion report for one input file."""

    source: str
    mode: str
    tool_version: str = __version__
    anonymized_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    )
    entity_counts: dict[str, int] = field(default_factory=dict)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    native: dict[str, Any] | None = None
    debug_log_path: str | None = None
    used_ocr: bool = False
    ocr: dict[str, Any] | None = None
    detector_sources: dict[str, int] | None = None
    lang_mode: str | None = None
    detected_languages: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Drop empty optional noise
        if not d.get("native"):
            d.pop("native", None)
        if not d.get("debug_log_path"):
            d.pop("debug_log_path", None)
        if not d.get("ocr"):
            d.pop("ocr", None)
        if not d.get("detector_sources"):
            d.pop("detector_sources", None)
        return d

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"

    def to_plain_text(self) -> str:
        lines = [
            f"Anonymizer {self.tool_version}",
            f"Source: {self.source}",
            f"Mode: {self.mode}",
            f"At: {self.anonymized_at}",
        ]
        if self.detected_languages:
            lines.append("Languages: " + ", ".join(self.detected_languages))
        if self.entity_counts:
            counts = ", ".join(
                f"{k}={v}" for k, v in sorted(self.entity_counts.items())
            )
            lines.append(f"Entities: {counts}")
        if self.detector_sources:
            ds = ", ".join(
                f"{k}={v}" for k, v in sorted(self.detector_sources.items())
            )
            lines.append(f"Detector sources: {ds}")
        if self.outputs:
            lines.append("Outputs:")
            for o in self.outputs:
                kind = o.get("kind", "?")
                path = o.get("path", "")
                note = o.get("note")
                meta = (
                    " (may carry source container metadata)"
                    if o.get("source_metadata_carried")
                    else " (rebuild — source metadata not carried)"
                )
                lines.append(f"  • [{kind}] {path}{meta}")
                if note:
                    lines.append(f"      {note}")
        if self.native:
            clean = self.native.get("native_clean")
            lines.append(f"Native clean: {clean}")
            nres = self.native.get("native_residuals") or 0
            if nres:
                samples = self.native.get("native_residual_samples") or []
                preview = ", ".join(repr(s[:40]) for s in samples[:5])
                lines.append(f"Native residuals: {nres} {preview}")
            nerr = self.native.get("native_scrub_errors") or 0
            if nerr:
                lines.append(f"Native scrub errors: {nerr}")
            cov = (self.native.get("native_coverage") or {}).get("guarantees")
            if cov:
                lines.append(f"Native coverage: {cov}")
        if self.used_ocr:
            lines.append("OCR: used")
            if self.ocr and self.ocr.get("residual_image_risk"):
                lines.append("OCR residual image risk: yes")
        if self.debug_log_path:
            lines.append(f"Debug log: {self.debug_log_path}")
        return "\n".join(lines) + "\n"

    def to_markdown(self) -> str:
        """Human-readable summary Markdown (sidecar — not the anonymized doc)."""
        lines = [
            f"# Anonymizer run summary ({self.tool_version})",
            "",
            f"- **Source:** `{self.source}`",
            f"- **Mode:** `{self.mode}`",
            f"- **At:** {self.anonymized_at}",
        ]
        if self.detected_languages:
            lines.append(
                "- **Languages:** " + ", ".join(f"`{x}`" for x in self.detected_languages)
            )
        if self.entity_counts:
            lines.append("- **Entity counts:**")
            for k, v in sorted(self.entity_counts.items()):
                lines.append(f"  - `{k}`: {v}")
        if self.detector_sources:
            lines.append("- **Detector sources:**")
            for k, v in sorted(self.detector_sources.items()):
                lines.append(f"  - `{k}`: {v}")
        if self.outputs:
            lines.append("- **Outputs:**")
            for o in self.outputs:
                carried = (
                    "may carry source metadata"
                    if o.get("source_metadata_carried")
                    else "rebuild — no source metadata"
                )
                lines.append(
                    f"  - `{o.get('kind')}`: `{o.get('path')}` ({carried})"
                )
        if self.native:
            lines.append(f"- **Native clean:** `{self.native.get('native_clean')}`")
            if self.native.get("native_residuals"):
                lines.append(
                    f"- **Native residuals:** {self.native.get('native_residuals')}"
                )
            if self.native.get("native_scrub_errors"):
                lines.append(
                    f"- **Native scrub errors:** {self.native.get('native_scrub_errors')}"
                )
        if self.debug_log_path:
            lines.append(f"- **Debug log:** `{self.debug_log_path}`")
        lines.append("")
        return "\n".join(lines)

    def save(self, path: Path | str, *, fmt: str | None = None) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        kind = (fmt or path.suffix.lstrip(".")).casefold()
        if kind in {"md", "markdown"}:
            path.write_text(self.to_markdown(), encoding="utf-8")
        else:
            if path.suffix.casefold() not in {".json", ".md", ".markdown"}:
                path = path.with_suffix(".json")
            path.write_text(self.to_json(), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return path


def summary_json_path_from_env() -> Path | None:
    """If ``ANONYMIZER_WRITE_SUMMARY_JSON`` is set, GUIs asked for a sidecar JSON."""
    raw = (os.environ.get("ANONYMIZER_WRITE_SUMMARY_JSON") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def write_summary_if_requested(summary: RunSummary) -> Path | None:
    """Append this run to a JSON **array** at ``ANONYMIZER_WRITE_SUMMARY_JSON``.

    GUIs set the env to a temp path before a batch; after the batch they read
    the array and show a completion dialog. Multi-file runs accumulate entries.
    """
    dest = summary_json_path_from_env()
    if dest is None:
        return None
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    items: list[Any] = []
    if dest.is_file():
        try:
            raw = json.loads(dest.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                items = raw
            elif isinstance(raw, dict):
                items = [raw]
        except (OSError, json.JSONDecodeError):
            items = []
    items.append(summary.to_dict())
    dest.write_text(
        json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    try:
        dest.chmod(0o600)
    except OSError:
        pass
    return dest


def load_summaries(path: Path | str) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def format_summaries_plain(summaries: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, d in enumerate(summaries):
        s = RunSummary(
            source=str(d.get("source") or ""),
            mode=str(d.get("mode") or ""),
            tool_version=str(d.get("tool_version") or __version__),
            anonymized_at=str(d.get("anonymized_at") or ""),
            entity_counts=dict(d.get("entity_counts") or {}),
            outputs=list(d.get("outputs") or []),
            native=d.get("native"),
            debug_log_path=d.get("debug_log_path"),
            used_ocr=bool(d.get("used_ocr")),
            ocr=d.get("ocr"),
            detector_sources=d.get("detector_sources"),
            lang_mode=d.get("lang_mode"),
            detected_languages=list(d.get("detected_languages") or []) or None,
        )
        if len(summaries) > 1:
            parts.append(f"—— File {i + 1} ——")
        parts.append(s.to_plain_text().rstrip())
    return "\n\n".join(parts) + ("\n" if parts else "")
