"""Write a redacted PDF by searching cleartext and applying black-box redactions."""

from __future__ import annotations

import logging
from pathlib import Path

from anonymizer.anonymize.surfaces import RedactSurface, surface_search_variants
from anonymizer.output.native_stats import NativeRedactStats

logger = logging.getLogger(__name__)


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

    Soft-wrapped or hyphenated names may miss — caller should report match rate.
    Does **not** scrub image-only text, all form widgets, or embedded files;
    document metadata is cleared best-effort.
    """
    import pymupdf as fitz

    source = Path(source)
    dest = Path(dest)
    stats = NativeRedactStats(format="pdf", surfaces_total=len(surfaces))
    if not surfaces:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
        stats.output_path = str(dest)
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

        # Best-effort metadata scrub (Author, Title, Keywords, …)
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
            # Drop XML metadata stream when present
            doc.del_xml_metadata()
        except Exception:  # noqa: BLE001
            pass
        try:
            doc.embfile_names()  # type: ignore[attr-defined]
            for name in list(doc.embfile_names()):  # type: ignore[attr-defined]
                try:
                    doc.embfile_del(name)  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

        dest.parent.mkdir(parents=True, exist_ok=True)
        doc.save(dest, garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
        stats.output_path = str(dest)
    finally:
        doc.close()

    return stats
