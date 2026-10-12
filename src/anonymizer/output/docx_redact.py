"""Write a redacted DOCX by replacing cleartext in paragraphs and tables."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from anonymizer.anonymize.surfaces import (
    RedactSurface,
    surface_search_variants,
)
from anonymizer.output.native_stats import NativeRedactStats
from anonymizer.output.native_verify import verify_docx_package

logger = logging.getLogger(__name__)

_AUTHOR_ATTRS = ("author", "initials", "date")


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


def _iter_package_xml_roots(doc) -> list:
    """Yield oxml roots for main document + related WordprocessingML parts."""
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    roots = [doc.element]
    seen: set[int] = {id(doc.element)}
    for rel in doc.part.rels.values():
        if rel.reltype not in (
            RT.FOOTNOTES,
            RT.ENDNOTES,
            RT.COMMENTS,
            RT.HEADER,
            RT.FOOTER,
        ):
            continue
        try:
            part = rel.target_part
            el = part.element
        except Exception:  # noqa: BLE001
            continue
        if id(el) in seen:
            continue
        seen.add(id(el))
        roots.append(el)
    return roots


def accept_tracked_changes(root) -> None:
    """Promote ``w:ins`` children and drop ``w:del`` / ``w:delText`` subtrees.

    After this, ``paragraph.text`` and run walks see the same insertions Word
    shows, and deleted revision text no longer survives in the package.
    """
    from docx.oxml.ns import qn

    # Drop deletions first (including nested)
    for el in list(root.iter(qn("w:del"))):
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)
    for el in list(root.iter(qn("w:delText"))):
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)

    # Unwrap insertions: move children up, remove the w:ins wrapper
    for el in list(root.iter(qn("w:ins"))):
        parent = el.getparent()
        if parent is None:
            continue
        idx = list(parent).index(el)
        for i, child in enumerate(list(el)):
            parent.insert(idx + i, child)
        parent.remove(el)


def scrub_revision_authors(root) -> None:
    """Blank w:author / w:initials / w:date on revision and comment marks."""
    from docx.oxml.ns import qn

    tags = (
        qn("w:ins"),
        qn("w:del"),
        qn("w:comment"),
        qn("w:commentRangeStart"),
        qn("w:commentRangeEnd"),
        qn("w:commentReference"),
    )
    for el in root.iter():
        if el.tag not in tags and not el.tag.endswith("}cellIns") and not el.tag.endswith(
            "}cellDel"
        ):
            # Also scrub any element that carries w:author
            if qn("w:author") not in el.attrib and qn("w:initials") not in el.attrib:
                continue
        for attr in _AUTHOR_ATTRS:
            key = qn(f"w:{attr}")
            if key in el.attrib:
                el.attrib[key] = ""


def scrub_hyperlink_targets(doc, surfaces: list[RedactSurface]) -> int:
    """Rewrite relationship Targets that contain a clear surface → about:blank.

    Returns number of targets rewritten.
    """
    n = 0
    clears = [s.clear for s in surfaces if s.clear]
    if not clears:
        return 0
    parts = [doc.part]
    try:
        for rel in doc.part.rels.values():
            try:
                parts.append(rel.target_part)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    seen: set[int] = set()
    for part in parts:
        if id(part) in seen:
            continue
        seen.add(id(part))
        try:
            rels = part.rels
        except Exception:  # noqa: BLE001
            continue
        for rel in rels.values():
            try:
                target = rel._target  # noqa: SLF001 — Relationship API
            except Exception:  # noqa: BLE001
                try:
                    target = rel.target_ref
                except Exception:  # noqa: BLE001
                    continue
            if not isinstance(target, str):
                continue
            if not any(c in target for c in clears):
                # casefold check for mailto names
                tcf = target.casefold()
                if not any(c.casefold() in tcf for c in clears):
                    continue
            try:
                rel._target = "about:blank"  # noqa: SLF001
                n += 1
            except Exception:  # noqa: BLE001
                try:
                    # Fallback: some python-docx builds use target_ref property
                    rel.target_ref = "about:blank"
                    n += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("hyperlink target scrub failed: %s", exc)
    return n


def _scrub_xml_blob_part(part, *, blank_locals: set[str] | None = None) -> bool:
    """Parse *part.blob* as XML, blank matching localnames / authorish attrs."""
    from xml.etree import ElementTree as ET

    blank_locals = blank_locals or set()
    try:
        root = ET.fromstring(part.blob)
    except Exception:  # noqa: BLE001
        return False
    changed = False
    for el in root.iter():
        local = el.tag.rsplit("}", 1)[-1]
        if local in blank_locals and (el.text or "").strip():
            el.text = ""
            changed = True
        for attr in list(el.attrib):
            al = attr.rsplit("}", 1)[-1].casefold()
            if al in {"author", "initials", "name", "displayname"} and el.attrib[attr]:
                el.attrib[attr] = ""
                changed = True
            if blank_locals and any(c.casefold() in (el.attrib[attr] or "").casefold() for c in blank_locals):
                # don't use blank_locals as surface list — skip
                pass
    if changed:
        part._blob = ET.tostring(root, encoding="utf-8", xml_declaration=True)  # noqa: SLF001
    return changed


def scrub_app_properties(doc) -> list[str]:
    """Blank Company/Manager (and similar) in docProps/app.xml."""
    errors: list[str] = []
    try:
        pkg = doc.part.package
        for part in pkg.parts:
            try:
                name = str(part.partname)
            except Exception:  # noqa: BLE001
                continue
            if "docProps" in name and name.endswith("app.xml"):
                _scrub_xml_blob_part(
                    part, blank_locals={"Company", "Manager", "HyperlinkBase"}
                )
                break
    except Exception as exc:  # noqa: BLE001
        msg = f"app.xml scrub failed: {exc}"
        logger.warning("%s", msg)
        errors.append(msg)
    return errors


def scrub_people_part(doc) -> None:
    """Best-effort: blank authorish attributes inside people.xml when present."""
    try:
        pkg = doc.part.package
        for part in pkg.parts:
            try:
                name = str(part.partname)
            except Exception:  # noqa: BLE001
                continue
            if name.endswith("people.xml"):
                _scrub_xml_blob_part(part, blank_locals=set())
    except Exception as exc:  # noqa: BLE001
        logger.debug("people.xml scrub skipped: %s", exc)


def prepare_docx_for_redaction(doc) -> list[str]:
    """Accept revisions + scrub authorship on all WordprocessingML roots."""
    errors: list[str] = []
    try:
        for root in _iter_package_xml_roots(doc):
            accept_tracked_changes(root)
            scrub_revision_authors(root)
    except Exception as exc:  # noqa: BLE001
        msg = f"revision accept/scrub failed: {exc}"
        logger.warning("%s", msg)
        errors.append(msg)
    scrub_people_part(doc)
    return errors


def redact_docx(
    source: Path,
    surfaces: list[RedactSurface],
    dest: Path,
    *,
    style: str = "placeholder",
) -> NativeRedactStats:
    """Copy *source* to *dest* with cleartext replaced per *style*.

    *style* ``placeholder`` inserts ``[TYPE_n]`` tags; ``remove`` deletes text.
    Accepts tracked changes first, walks headers/footers/tables/notes/comments/
    text boxes, scrubs core/app properties and matching hyperlink targets, then
    verifies via an independent zip scan.
    """
    from docx import Document

    source = Path(source)
    dest = Path(dest)
    stats = NativeRedactStats(format="docx", surfaces_total=len(surfaces))
    scrub_errs: list[str] = []
    if style not in ("placeholder", "remove"):
        style = "placeholder"

    doc = Document(str(source))
    scrub_errs.extend(prepare_docx_for_redaction(doc))

    if not surfaces:
        dest.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(dest))
        stats.output_path = str(dest)
        stats.verified = True
        stats.scrub_errors = len(scrub_errs)
        stats.scrub_error_samples = scrub_errs[:8]
        return stats

    found: set[str] = set()
    seen_p: set[int] = set()
    for paragraph in _iter_all_paragraphs(doc):
        try:
            key = id(paragraph._element)  # noqa: SLF001
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
        msg = f"core_properties scrub failed: {exc}"
        logger.warning("%s", msg)
        scrub_errs.append(msg)

    scrub_errs.extend(scrub_app_properties(doc))
    try:
        scrub_hyperlink_targets(doc, surfaces)
    except Exception as exc:  # noqa: BLE001
        msg = f"hyperlink scrub failed: {exc}"
        logger.warning("%s", msg)
        scrub_errs.append(msg)

    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dest))
    stats.output_path = str(dest)

    residuals = verify_docx_package(dest, surfaces)
    stats.verified = True
    stats.residuals_found = len(residuals)
    stats.residuals = residuals
    # Surfaces destroyed via accept-revisions / package scrub (not paragraph hits)
    # should not count as layout misses when the independent verify is clean.
    if stats.missed:
        residual_set = set(residuals)
        still_missed: list[str] = []
        for clear in stats.missed:
            if clear in residual_set:
                still_missed.append(clear)
            else:
                stats.surfaces_found += 1
                stats.surfaces_missed = max(0, stats.surfaces_missed - 1)
        stats.missed = still_missed
    stats.scrub_errors = len(scrub_errs)
    stats.scrub_error_samples = scrub_errs[:8]
    return stats
