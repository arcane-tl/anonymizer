"""Write a redacted DOCX by replacing cleartext in paragraphs and tables."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from anonymizer.anonymize.surfaces import (
    RedactSurface,
    surface_appears_in_text,
    surface_search_variants,
)
from anonymizer.output.native_stats import NativeRedactStats

logger = logging.getLogger(__name__)


def _find_match_spans(full: str, clear: str) -> list[tuple[int, int]]:
    """Return non-overlapping ``[start, end)`` spans for *clear* and variants."""
    spans: list[tuple[int, int]] = []
    occupied = [False] * len(full)
    # Longer variants first so ``ETA-maat`` wins over ``ETA``
    variants = sorted(surface_search_variants(clear), key=lambda v: (-len(v), v))
    for variant in variants:
        if not variant:
            continue
        start = 0
        while True:
            i = full.find(variant, start)
            if i < 0:
                break
            j = i + len(variant)
            if not any(occupied[i:j]):
                spans.append((i, j))
                for k in range(i, j):
                    occupied[k] = True
            start = i + 1
    spans.sort()
    return spans


def _redact_paragraph(paragraph, surfaces: list[RedactSurface], style: str) -> tuple[int, set[str]]:
    """Redact all surfaces in one paragraph. Returns hit count and found clears."""
    full = paragraph.text
    if not full:
        return 0, set()

    # Build combined replacement plan on the original string, longest surface first
    # (surfaces are already sorted longest-first by surfaces_from_mapping).
    occupied = [False] * len(full)
    planned: list[tuple[int, int, str, str]] = []  # start, end, replacement, clear
    found: set[str] = set()
    hits = 0

    for surface in surfaces:
        replacement = "" if style == "remove" else surface.placeholder
        for a, b in _find_match_spans(full, surface.clear):
            if any(occupied[a:b]):
                continue
            planned.append((a, b, replacement, surface.clear))
            for k in range(a, b):
                occupied[k] = True
            found.add(surface.clear)
            hits += 1

    if not planned:
        return 0, set()

    # Group consecutive spans that share the same replacement? Not needed —
    # apply each span with its own replacement right-to-left.
    planned.sort(key=lambda x: x[0])
    # Apply via run-aware path when runs exist; fall back to whole-paragraph rewrite
    runs = list(paragraph.runs)
    if runs and "".join(r.text or "" for r in runs) == full:
        # Apply right-to-left one span at a time (replacement may differ per surface)
        texts = [r.text or "" for r in runs]
        run_spans: list[tuple[int, int, int]] = []
        pos = 0
        for i, t in enumerate(texts):
            run_spans.append((i, pos, pos + len(t)))
            pos += len(t)

        def locate(index: int, *, end: bool = False) -> tuple[int, int]:
            if end and index == pos and run_spans:
                i, s, _e = run_spans[-1]
                return i, index - s
            for i, s, e in run_spans:
                if s <= index < e:
                    return i, index - s
                if end and index == e and (s < e or s == e):
                    return i, index - s
            i, s, _e = run_spans[-1]
            return i, index - s

        for a, b, replacement, _clear in reversed(planned):
            first, first_off = locate(a)
            last, last_off = locate(b, end=True)
            if first == last:
                t = texts[first]
                texts[first] = t[:first_off] + replacement + t[last_off:]
            else:
                texts[first] = texts[first][:first_off] + replacement
                for i in range(first + 1, last):
                    texts[i] = ""
                texts[last] = texts[last][last_off:]

        for run, text in zip(runs, texts, strict=True):
            run.text = text

        if style == "remove":
            # Collapse leftover multi-spaces inside runs only (keep structure)
            for run in runs:
                if run.text and "  " in run.text:
                    run.text = re.sub(r"[^\S\n]{2,}", " ", run.text)
    else:
        new_full = full
        # Apply from mapping built on original — safer via piece rebuild
        pieces: list[str] = []
        last = 0
        for a, b, replacement, _clear in planned:
            pieces.append(full[last:a])
            pieces.append(replacement)
            last = b
        pieces.append(full[last:])
        new_full = "".join(pieces)
        if style == "remove":
            new_full = re.sub(r"[^\S\n]{2,}", " ", new_full)
        if not runs:
            paragraph.add_run(new_full)
        else:
            runs[0].text = new_full
            for run in runs[1:]:
                run.text = ""

    return hits, found


def _iter_table_paragraphs(table):
    """Yield paragraphs in a table, including nested tables."""
    for row in table.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                yield p
            for nested in cell.tables:
                yield from _iter_table_paragraphs(nested)


def _iter_header_footer_paragraphs(part) -> None:
    if part is None:
        return
    try:
        for p in part.paragraphs:
            yield p
        for table in part.tables:
            yield from _iter_table_paragraphs(table)
    except Exception:  # noqa: BLE001 — linked section parts
        return


def _iter_oxml_paragraphs(element, part):
    """Yield ``Paragraph`` wrappers for every ``w:p`` under *element*."""
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph

    for el in element.iter(qn("w:p")):
        yield Paragraph(el, part)


def _iter_all_paragraphs(doc):
    """Body, nested tables, headers/footers, comments, footnotes, endnotes, text boxes."""
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    for p in doc.paragraphs:
        yield p
    for table in doc.tables:
        yield from _iter_table_paragraphs(table)

    for section in doc.sections:
        for part in (
            section.header,
            section.footer,
            section.first_page_header,
            section.first_page_footer,
            section.even_page_header,
            section.even_page_footer,
        ):
            yield from _iter_header_footer_paragraphs(part)

    # Comments via python-docx API (deduped later by paragraph element id)
    try:
        for comment in doc.part.comments:
            for p in comment.paragraphs:
                yield p
            for table in comment.tables:
                yield from _iter_table_paragraphs(table)
    except Exception as exc:  # noqa: BLE001
        logger.debug("comment iteration failed: %s", exc)

    # Footnotes / endnotes / comments part (oxml) — covers API gaps
    seen_parts: set[int] = set()
    for rel in doc.part.rels.values():
        if rel.reltype not in (RT.FOOTNOTES, RT.ENDNOTES, RT.COMMENTS):
            continue
        try:
            part = rel.target_part
        except Exception:  # noqa: BLE001
            continue
        part_id = id(part)
        if part_id in seen_parts:
            continue
        seen_parts.add(part_id)
        try:
            yield from _iter_oxml_paragraphs(part.element, part)
        except Exception as exc:  # noqa: BLE001
            logger.debug("related part paragraph iter failed: %s", exc)

    # Text boxes / frames inside the main document body
    try:
        from docx.oxml.ns import qn

        body = doc.element.body
        for txbx in body.iter(qn("w:txbxContent")):
            yield from _iter_oxml_paragraphs(txbx, doc.part)
    except Exception as exc:  # noqa: BLE001
        logger.debug("textbox iteration failed: %s", exc)


def redact_docx(
    source: Path,
    surfaces: list[RedactSurface],
    dest: Path,
    *,
    style: str = "placeholder",
) -> NativeRedactStats:
    """Copy *source* to *dest* with cleartext replaced per *style*.

    *style* ``placeholder`` inserts ``[TYPE_n]`` tags; ``remove`` deletes text.
    Cross-run matches keep unaffected run formatting; the replacement is placed
    in the first affected run. Also walks headers/footers, nested tables,
    comments, footnotes/endnotes, and text boxes.
    """
    from docx import Document

    source = Path(source)
    dest = Path(dest)
    stats = NativeRedactStats(format="docx", surfaces_total=len(surfaces))
    if style not in ("placeholder", "remove"):
        style = "placeholder"

    doc = Document(str(source))
    if not surfaces:
        dest.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(dest))
        stats.output_path = str(dest)
        stats.verified = True
        return stats

    found: set[str] = set()
    # Deduplicate paragraph elements (headers may be linked; oxml iter may overlap)
    seen_p: set[int] = set()
    for paragraph in _iter_all_paragraphs(doc):
        try:
            key = id(paragraph._element)  # noqa: SLF001 — stable identity
        except Exception:  # noqa: BLE001
            key = id(paragraph)
        if key in seen_p:
            continue
        seen_p.add(key)
        n, clears = _redact_paragraph(paragraph, surfaces, style)
        if n:
            found.update(clears)
            stats.hit_count += n

    for surface in surfaces:
        if surface.clear in found:
            stats.surfaces_found += 1
        else:
            stats.surfaces_missed += 1
            stats.missed.append(surface.clear)

    # Best-effort document property scrub (Author, Title, …)
    try:
        props = doc.core_properties
        for attr in (
            "author",
            "category",
            "comments",
            "content_status",
            "identifier",
            "keywords",
            "last_modified_by",
            "subject",
            "title",
        ):
            try:
                setattr(props, attr, None)
            except (AttributeError, ValueError, TypeError):
                try:
                    setattr(props, attr, "")
                except (AttributeError, ValueError, TypeError):
                    pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("core_properties scrub failed: %s", exc)

    # Post-redaction verification
    haystack = "\n".join(p.text for p in _iter_all_paragraphs(doc) if p.text)
    residuals: list[str] = []
    seen_res: set[str] = set()
    for surface in surfaces:
        if surface.clear in seen_res:
            continue
        if surface_appears_in_text(haystack, surface.clear):
            residuals.append(surface.clear)
            seen_res.add(surface.clear)
    stats.verified = True
    stats.residuals_found = len(residuals)
    stats.residuals = residuals

    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dest))
    stats.output_path = str(dest)
    return stats
