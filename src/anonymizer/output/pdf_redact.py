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
                tname = (
                    type_info[1]
                    if isinstance(type_info, tuple) and len(type_info) > 1
                    else ""
                )
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


def _inventory_images(doc) -> tuple[int, list[int]]:
    """Return ``(total_images, 1-based page numbers that contain images)``."""
    total = 0
    pages: list[int] = []
    for i, page in enumerate(doc):
        try:
            imgs = page.get_images(full=True) or []
        except Exception:  # noqa: BLE001
            imgs = []
        n = len(imgs)
        if n:
            total += n
            pages.append(i + 1)
    return total, pages


def _page_image_rects(page) -> list:
    """Bounding boxes for images placed on *page*."""
    rects = []
    try:
        infos = page.get_images(full=True) or []
    except Exception:  # noqa: BLE001
        return rects
    for info in infos:
        xref = info[0]
        try:
            found = page.get_image_rects(xref) or []
        except Exception:  # noqa: BLE001
            continue
        rects.extend(found)
    return rects


def _redact_letterhead_images(
    doc,
    *,
    fill: tuple[float, float, float],
    top_frac: float = 0.30,
    bottom_frac: float = 0.32,
) -> int:
    """Black-box images in header/footer bands and repeating page chrome logos.

    Covers:
    - Top/bottom page bands (letterhead / footer marks) on every page
    - Images whose xref appears on most pages (running logo chrome)

    Returns number of image rects marked for redaction. Caller must
    ``apply_redactions``.
    """
    page_count = max(int(doc.page_count), 1)
    # xref → pages it appears on (1-based) — running logos hit many pages
    xref_pages: dict[int, set[int]] = {}
    page_rects: list[list] = []
    for page_index, page in enumerate(doc):
        rects_here = []
        try:
            infos = page.get_images(full=True) or []
        except Exception:  # noqa: BLE001
            infos = []
        for info in infos:
            xref = info[0]
            try:
                found = page.get_image_rects(xref) or []
            except Exception:  # noqa: BLE001
                found = []
            if found:
                xref_pages.setdefault(xref, set()).add(page_index + 1)
                for rect in found:
                    rects_here.append((xref, rect))
        page_rects.append(rects_here)

    running = {
        xref
        for xref, pages in xref_pages.items()
        if len(pages) >= max(2, (page_count + 1) // 2)
    }

    n = 0
    for page_index, page in enumerate(doc):
        page_h = float(page.rect.height) or 1.0
        top_y = page_h * top_frac
        bottom_y = page_h * (1.0 - bottom_frac)
        for xref, rect in page_rects[page_index]:
            try:
                y0, y1 = float(rect.y0), float(rect.y1)
            except Exception:  # noqa: BLE001
                continue
            in_top = y1 <= top_y or y0 <= page_h * 0.10
            in_bottom = y0 >= bottom_y
            cover = bool(in_top or in_bottom or xref in running)
            if not cover:
                continue
            try:
                page.add_redact_annot(rect, fill=fill)
                n += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("letterhead redact failed: %s", exc)
    return n


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
    redact_letterhead_images: bool = False,
) -> NativeRedactStats:
    """Copy *source* to *dest* with black-box redaction over each surface.

    Uses PyMuPDF ``search_for`` + ``add_redact_annot`` / ``apply_redactions`` so
    text is removed from the content stream (not merely covered).

    After redaction: scrub form widgets and annotations, wipe metadata, then
    re-extract text to populate residual stats. Soft-wrapped mid-glyph splits
    and image-only text may still miss — check ``stats.residuals`` / ``is_clean``.

    When *redact_letterhead_images* is True, images in header/footer bands
    (especially page 1) are blacked out as well.
    """
    import pymupdf as fitz

    source = Path(source)
    dest = Path(dest)
    stats = NativeRedactStats(format="pdf", surfaces_total=len(surfaces))

    doc = fitz.open(source)
    try:
        img_total, img_pages = _inventory_images(doc)
        stats.images_total = img_total
        stats.image_pages = img_pages

        if not surfaces and not redact_letterhead_images:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
            stats.output_path = str(dest)
            stats.verified = True
            return stats

        found_surfaces: set[str] = set()
        for page in doc:
            for surface in surfaces:
                page_hits = 0
                for variant in surface_search_variants(surface.clear):
                    try:
                        rects = page.search_for(variant)
                    except Exception as exc:  # noqa: BLE001 — layout quirks
                        logger.debug(
                            "search_for failed for %r: %s", variant[:40], exc
                        )
                        continue
                    for rect in rects:
                        page.add_redact_annot(rect, fill=fill)
                        page_hits += 1
                        stats.hit_count += 1
                if page_hits:
                    found_surfaces.add(surface.clear)

        letterhead_n = 0
        if redact_letterhead_images:
            letterhead_n = _redact_letterhead_images(doc, fill=fill)
            stats.letterhead_redacted = letterhead_n > 0
            stats.images_redacted = letterhead_n

        for page in doc:
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

        residuals = _verify_residuals(doc, surfaces) if surfaces else []
        stats.verified = True
        stats.residuals_found = len(residuals)
        stats.residuals = residuals

        dest.parent.mkdir(parents=True, exist_ok=True)
        doc.save(dest, garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
        stats.output_path = str(dest)
    finally:
        doc.close()

    return stats
