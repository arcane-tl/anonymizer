"""Golden leak corpus: channels that used to report clean while retaining PII."""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from anonymizer.anonymize.surfaces import RedactSurface
from anonymizer.extract.docx_extract import extract_docx
from anonymizer.output.docx_redact import redact_docx
from anonymizer.output.native_verify import verify_docx_package, verify_pdf_file
from anonymizer.output.pdf_redact import redact_pdf

NAME = "Maija Korhonen"
SECRET_DEL = "SecretDelName"


def _surface(clear: str) -> RedactSurface:
    return RedactSurface(clear=clear, placeholder="[PERSON_1]")


def _docx_with_revision_and_author(path: Path) -> None:
    doc = Document()
    p = doc.add_paragraph("Hello ")
    ins = OxmlElement("w:ins")
    ins.set(qn("w:author"), NAME)
    ins.set(qn("w:date"), "2020-01-01T00:00:00Z")
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = NAME
    t.set(qn("xml:space"), "preserve")
    r.append(t)
    ins.append(r)
    p._p.append(ins)

    deleted = OxmlElement("w:del")
    deleted.set(qn("w:author"), NAME)
    dr = OxmlElement("w:r")
    dt = OxmlElement("w:delText")
    dt.text = SECRET_DEL
    dt.set(qn("xml:space"), "preserve")
    dr.append(dt)
    deleted.append(dr)
    p._p.append(deleted)

    doc.core_properties.author = NAME
    doc.save(path)

    # Inject Company into app.xml
    import zipfile
    from xml.etree import ElementTree as ET

    buf = path.read_bytes()
    tmp = path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(path, "r") as zin, zipfile.ZipFile(tmp, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith("docProps/app.xml"):
                root = ET.fromstring(data)
                ns = {"ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"}
                company = root.find("ep:Company", ns)
                if company is None:
                    company = ET.SubElement(
                        root,
                        "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}Company",
                    )
                company.text = NAME
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(item, data)
    tmp.replace(path)


def test_pdf_toc_cleared_and_independent_verify(tmp_path: Path):
    src = tmp_path / "toc.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), f"Hello {NAME}")
    doc.set_toc([[1, f"Signature — {NAME}", 1]])
    doc.save(src)
    doc.close()

    dest = tmp_path / "toc.out.pdf"
    stats = redact_pdf(src, [_surface(NAME)], dest)
    assert stats.is_clean, (stats.residuals, stats.scrub_error_samples, stats.summary())
    assert stats.residuals == []
    out = fitz.open(dest)
    try:
        assert out.get_toc() == []
        assert NAME not in (out[0].get_text() or "")
    finally:
        out.close()
    assert verify_pdf_file(dest, [_surface(NAME)]) == []


def test_docx_revision_author_app_cleared(tmp_path: Path):
    src = tmp_path / "rev.docx"
    _docx_with_revision_and_author(src)
    # Independent verify must see the leak before redaction
    before = verify_docx_package(src, [_surface(NAME), _surface(SECRET_DEL)])
    assert NAME in before

    dest = tmp_path / "rev.out.docx"
    stats = redact_docx(src, [_surface(NAME), _surface(SECRET_DEL)], dest)
    assert stats.residuals == [], stats.residuals
    assert stats.is_clean, (stats.summary(), stats.scrub_error_samples)
    after = verify_docx_package(dest, [_surface(NAME), _surface(SECRET_DEL)])
    assert after == []


def test_extract_sees_tracked_insertion(tmp_path: Path):
    src = tmp_path / "ins.docx"
    _docx_with_revision_and_author(src)
    extracted = extract_docx(src)
    joined = "\n".join(b.text for b in extracted.blocks)
    assert NAME in joined
