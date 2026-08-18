"""Write a redacted PDF by searching cleartext and applying black-box redactions."""

from __future__ import annotations

import logging
from pathlib import Path

from anonymizer.anonymize.surfaces import (
    RedactSurface,
    surface_appears_in_text,
    surface_search_variants,
)
from anonymizer.output.native_stats import NativeRedactStats

logger = logging.getLogger(__name__)


def _scrub_annotations_and_forms(doc) -> tuple[int, int]:
    """Remove form widgets and non-redact annotations (comments, free text, …).

    Returns ``(annotations_scrubbed, widgets_scrubbed)``.
    """
    ann_count = 0
    widget_count = 0
    for page in doc:
        # Widgets first — field values often hold PII outside the body text layer.
        try:
            widgets = list(page.widgets() or [])
        except Exception:  # noqa: BLE001
            widgets = []
        for widget in widgets:
            try:
                page.delete_widget(widget)
                widget_count += 1
            except Exception:  # noqa: BLE001
                try:
                    widget.field_value = ""
                    widget.update()
                    widget_count += 1
                except Exception as exc:  # noqa: BLE001
                    logger.debug("widget scrub failed: %s", exc)

        try:
            annots = list(page.annots() or [])
        except Exception:  # noqa: BLE001
            annots = []
        for annot in annots:
            try:
                type_info = annot.type
                tname = type_info[1] if isinstance(type_info, tuple) and len(type_info) > 1 else ""
                if tname == "Redact":
                    continue
                page.delete_annot(annot)
                ann_count += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("annot scrub failed: %s", exc)

    return ann_count, widget_count


def _scrub_metadata(doc) -> None:
    """Best-effort document info / XML metadata / embedded-file wipe."""
    try:
        doc.set_metadata(
            {
                "title": "",
                "author": "",
                "subject": "",
                "keywords": "",
                "creator": "",
                "producer": "anonymizer",
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("set_metadata failed: %s", exc)
    try:
        doc.del_xml_metadata()
    except Exception:  # noqa: BLE001
        pass
    try:
        for name in list(doc.embfile_names()):  # type: ignore[attr-defined]
            try:
                doc.embfile_del(name)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass


def _verify_residuals(doc, surfaces: list[RedactSurface]) -> list[str]:
    """Re-extract page text and return clears that still appear."""
    chunks: list[str] = []
    for page in doc:
        try:
            chunks.append(page.get_text() or "")
        except Exception as exc:  # noqa: BLE001
            logger.debug("get_text failed during verify: %s", exc)
    haystack = "\n".join(chunks)
    residual: list[str] = []
    seen: set[str] = set()
    for surface in surfaces:
        if surface.clear in seen:
            continue
        if surface_appears_in_text(haystack, surface.clear):
            residual.append(surface.clear)
            seen.add(surface.clear)
    return residual


def redact_pdf(
    source: Path,
    surfaces: list[RedactSurface],
    dest: Path,
    *,
    fill: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> NativeRedactStats:
    """Copy *source* to *dest* with black-box redaction over each surface.

    Uses PyMuPDF ``search_for`` + ``add_redact_annot`` / ``apply_redactions`` so
    text is removed from the content stream (not merely covered).

    After redaction: scrub form widgets and annotations, wipe metadata, then
    re-extract text to populate residual stats. Soft-wrapped mid-glyph splits
    and image-only text may still miss — check ``stats.residuals`` / ``is_clean``.
    """
    import pymupdf as fitz

    source = Path(source)
    dest = Path(dest)
    stats = NativeRedactStats(format="pdf", surfaces_total=len(surfaces))
    if not surfaces:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
        stats.output_path = str(dest)
        stats.verified = True
        return stats

    doc = fitz.open(source)
    try:
        found_surfaces: set[str] = set()
        for page in doc:
            for surface in surfaces:
                page_hits = 0
                for variant in surface_search_variants(surface.clear):
                    try:
                        rects = page.search_for(variant)
                    except Exception as exc:  # noqa: BLE001 — layout quirks
                        logger.debug("search_for failed for %r: %s", variant[:40], exc)
                        continue
                    for rect in rects:
                        page.add_redact_annot(rect, fill=fill)
                        page_hits += 1
                        stats.hit_count += 1
                if page_hits:
                    found_surfaces.add(surface.clear)
            page.apply_redactions()

        for surface in surfaces:
            if surface.clear in found_surfaces:
                stats.surfaces_found += 1
            else:
                stats.surfaces_missed += 1
                stats.missed.append(surface.clear)

        ann_n, widget_n = _scrub_annotations_and_forms(doc)
        stats.annotations_scrubbed = ann_n
        stats.widgets_scrubbed = widget_n
        _scrub_metadata(doc)

        residuals = _verify_residuals(doc, surfaces)
        stats.verified = True
        stats.residuals_found = len(residuals)
        stats.residuals = residuals

        dest.parent.mkdir(parents=True, exist_ok=True)
        doc.save(dest, garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
        stats.output_path = str(dest)
    finally:
        doc.close()

    return stats
