"""Independent residual checks for native PDF/DOCX (not the redaction walker).

These verifiers deliberately avoid ``paragraph.text`` / page-only walks used
during redaction so silent misses in revisions, outline, rels, etc. show up.
"""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path

from anonymizer.anonymize.surfaces import (
    RedactSurface,
    surface_appears_in_text,
    surface_search_variants,
)

logger = logging.getLogger(__name__)

# Strip tags but keep attribute values in the haystack (authors, targets, …)
_XML_TAG_RE = re.compile(r"<[^>]+>")


def _surface_in_haystack(haystack: str, clear: str) -> bool:
    if not clear or not haystack:
        return False
    if surface_appears_in_text(haystack, clear):
        return True
    # Raw bytes / compressed XML may not match repaired variants — try literals
    for variant in surface_search_variants(clear):
        if variant and variant in haystack:
            return True
        if variant and variant.casefold() in haystack.casefold():
            return True
    return False


def find_residuals_in_text(haystack: str, surfaces: list[RedactSurface]) -> list[str]:
    """Return unique clear surfaces that still appear in *haystack*."""
    found: list[str] = []
    seen: set[str] = set()
    for surface in surfaces:
        clear = surface.clear
        if not clear or clear in seen:
            continue
        if _surface_in_haystack(haystack, clear):
            found.append(clear)
            seen.add(clear)
    return found


def verify_docx_package(
    path: Path | str,
    surfaces: list[RedactSurface],
) -> list[str]:
    """Unzip DOCX and scan every part (text + attribute values) for surfaces."""
    path = Path(path)
    if not surfaces:
        return []
    chunks: list[str] = []
    try:
        with zipfile.ZipFile(path, "r") as zf:
            for name in zf.namelist():
                try:
                    raw = zf.read(name)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("docx verify read %s failed: %s", name, exc)
                    continue
                # Decode XML/rels as text; skip obvious binaries
                if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".emf", ".wmf", ".bin")):
                    continue
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        text = raw.decode("utf-8", errors="replace")
                    except Exception:  # noqa: BLE001
                        continue
                # Keep attribute values: crude strip of tags leaves quoted attrs
                # by also appending raw text
                chunks.append(text)
                chunks.append(_XML_TAG_RE.sub(" ", text))
    except Exception as exc:  # noqa: BLE001
        logger.warning("docx independent verify failed: %s", exc)
        # Fail closed on verify error — treat all surfaces as residual signal
        return [s.clear for s in surfaces if s.clear]

    haystack = "\n".join(chunks)
    return find_residuals_in_text(haystack, surfaces)


def verify_pdf_document(
    doc,
    surfaces: list[RedactSurface],
    *,
    max_xrefs: int = 4000,
) -> list[str]:
    """Scan PDF text layer, TOC titles, and a bounded xref object dump."""
    if not surfaces:
        return []
    parts: list[str] = []
    try:
        for page in doc:
            try:
                parts.append(page.get_text() or "")
            except Exception as exc:  # noqa: BLE001
                logger.debug("pdf verify get_text failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("pdf verify page iter failed: %s", exc)

    try:
        for _lvl, title, _page in doc.get_toc() or []:
            if title:
                parts.append(str(title))
    except Exception as exc:  # noqa: BLE001
        logger.debug("pdf verify get_toc failed: %s", exc)

    try:
        xref_n = int(doc.xref_length())
    except Exception:  # noqa: BLE001
        xref_n = 0
    limit = min(xref_n, max_xrefs)
    for xref in range(1, limit):
        try:
            obj = doc.xref_object(xref) or ""
        except Exception:  # noqa: BLE001
            continue
        if obj:
            parts.append(obj)

    haystack = "\n".join(parts)
    return find_residuals_in_text(haystack, surfaces)


def verify_pdf_file(path: Path | str, surfaces: list[RedactSurface]) -> list[str]:
    """Open *path* with PyMuPDF and run :func:`verify_pdf_document`."""
    import pymupdf as fitz

    path = Path(path)
    doc = fitz.open(path)
    try:
        return verify_pdf_document(doc, surfaces)
    finally:
        doc.close()
