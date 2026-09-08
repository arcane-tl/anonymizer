"""Windows/options GUI theme helpers (icon path + no display required)."""

from __future__ import annotations

from pathlib import Path

from anonymizer.gui.app import (
    FORMAT_DISPLAY,
    FORMAT_LABELS,
    MODE_LABELS,
    STYLE_LABELS,
    _files_list_column_count,
    _files_list_height_px,
    _files_list_row_count,
    _filter_paths,
    _guess_outputs,
    _label_for,
    _templates_status,
    _unsupported_paths_notice,
    _value_for,
    format_kinds_from_flags,
    format_selection_status,
    resolve_dialog_icon_path,
    toggle_format_order,
)
from anonymizer.anonymize.templates import Template
from anonymizer.util.files import SUPPORTED_TYPES_README_URL, unsupported_type_notice


def test_resolve_dialog_icon_path_finds_packaged_asset():
    path = resolve_dialog_icon_path()
    assert path is not None, "expected Anonymizer-dialog.png (or Mac packaging fallback)"
    assert path.is_file()
    assert path.suffix.lower() == ".png"
    # Prefer the shipped GUI asset when present
    packaged = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "anonymizer"
        / "gui"
        / "assets"
        / "Anonymizer-dialog.png"
    )
    if packaged.is_file():
        assert path.resolve() == packaged.resolve()


def test_format_labels_match_cli_formats():
    keys = [k for k, _ in FORMAT_LABELS]
    assert keys == ["md", "source", "pdf"]
    assert FORMAT_DISPLAY["source"].startswith("Source filetype")
    assert FORMAT_DISPLAY["pdf"] == "PDF text"


def test_format_kinds_from_flags():
    assert format_kinds_from_flags(md=True, source=False, pdf=False) == ["md"]
    assert format_kinds_from_flags(md=False, source=True, pdf=True) == [
        "source",
        "pdf",
    ]
    assert format_kinds_from_flags(
        md=True, source=True, pdf=True, mode="extract"
    ) == ["md", "pdf"]
    assert format_kinds_from_flags(md=False, source=False, pdf=False) == []
    # Prefer click order when provided
    assert format_kinds_from_flags(
        md=True, source=True, pdf=False, order=["source", "md"]
    ) == ["source", "md"]


def test_format_selection_status_numbered():
    assert format_selection_status([]) == "None selected"
    assert format_selection_status(["md"]) == "1. Markdown"
    text = format_selection_status(["source", "md", "pdf"])
    assert text.startswith("1. Source filetype")
    assert "2. Markdown" in text
    assert "3. PDF text" in text


def test_toggle_format_order():
    order: list[str] = []
    order = toggle_format_order(order, "md", True)
    assert order == ["md"]
    order = toggle_format_order(order, "pdf", True)
    assert order == ["md", "pdf"]
    order = toggle_format_order(order, "md", False)
    assert order == ["pdf"]
    order = toggle_format_order(order, "source", True)
    assert order == ["pdf", "source"]


def test_unsupported_paths_notice_for_pages(tmp_path: Path):
    pages = tmp_path / "Brief.pages"
    pages.write_bytes(b"x")
    assert _filter_paths([str(pages)]) == []
    notice = _unsupported_paths_notice([str(pages)])
    assert notice.startswith("Unsupported file type")
    assert "Brief.pages" in notice
    assert "Pages" in notice
    assert notice.rstrip().endswith(SUPPORTED_TYPES_README_URL)


def test_unsupported_paths_notice_for_gdoc(tmp_path: Path):
    gdoc = tmp_path / "Notes.gdoc"
    gdoc.write_text("{}", encoding="utf-8")
    notice = _unsupported_paths_notice([str(gdoc)])
    assert "Google Docs" in notice
    assert ".gdoc" in notice
    assert notice.rstrip().endswith(SUPPORTED_TYPES_README_URL)


def test_unsupported_type_notice_body_omits_url_for_gui():
    n = unsupported_type_notice(".pages", path_hint="Brief.pages")
    body = n.body(include_url=False)
    assert SUPPORTED_TYPES_README_URL not in body
    assert "Brief.pages" in body
    assert n.url == SUPPORTED_TYPES_README_URL


def test_mode_and_style_label_keys():
    assert [k for k, _ in MODE_LABELS] == ["strict", "standard", "extract"]
    assert [k for k, _ in STYLE_LABELS] == ["placeholder", "remove"]
    assert "Strict" in MODE_LABELS[0][1]
    assert "placeholders" in STYLE_LABELS[0][1]


def test_label_value_roundtrip():
    assert _value_for(MODE_LABELS, _label_for(MODE_LABELS, "standard")) == "standard"
    assert _value_for(FORMAT_LABELS, FORMAT_DISPLAY["source"]) == "source"
    assert _value_for(FORMAT_LABELS, "PDF text") == "pdf"


def test_guess_outputs_respects_format(tmp_path: Path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    md = tmp_path / "doc.anonymized.md"
    md.write_text("# x\n", encoding="utf-8")
    native = tmp_path / "doc.anonymized.pdf"
    native.write_bytes(b"%PDF")
    text_pdf = tmp_path / "doc.anonymized.text.pdf"
    text_pdf.write_bytes(b"%PDF")

    only_md = _guess_outputs([pdf], "strict", "md")
    assert only_md == [str(md)]

    only_src = _guess_outputs([pdf], "strict", "source")
    assert only_src == [str(native)]

    both = _guess_outputs([pdf], "strict", "md,source")
    assert both == [str(md), str(native)]

    # Compat alias both → md,source
    both_alias = _guess_outputs([pdf], "strict", "both")
    assert both_alias == [str(md), str(native)]

    # Extract never returns native even if format says both
    extracted = tmp_path / "doc.md"
    extracted.write_text("t\n", encoding="utf-8")
    extract_outs = _guess_outputs([pdf], "extract", "both")
    assert extract_outs == [str(extracted)]

    with_text = _guess_outputs([pdf], "strict", "md,pdf")
    assert with_text == [str(md), str(text_pdf)]

    all_three = _guess_outputs([pdf], "strict", "md,source,pdf")
    assert all_three == [str(md), str(native), str(text_pdf)]

    pdf_only = _guess_outputs([pdf], "strict", "pdf")
    assert pdf_only == [str(text_pdf)]


def test_templates_status_mac_style():
    """Active templates line: no count prefix or Templates… suffix."""
    assert _templates_status([], []) == "No templates selected"
    packs = [
        Template(id="a", title="Alpha", builtin=True),
        Template(id="b", title="Beta", builtin=False),
    ]
    line = _templates_status(["a", "b"], packs)
    assert line == "Alpha, Beta"
    assert "template(s)" not in line
    assert "Templates" not in line
    # Unknown id falls back to the id string
    assert _templates_status(["missing"], packs) == "missing"


def test_files_list_layout_helpers():
    assert _files_list_column_count(0) == 1
    assert _files_list_column_count(1) == 1
    assert _files_list_column_count(2) == 2
    assert _files_list_column_count(5) == 2
    assert _files_list_row_count(1) == 1
    assert _files_list_row_count(2) == 1
    assert _files_list_row_count(3) == 2
    assert _files_list_row_count(4) == 2
    h1 = _files_list_height_px(1)
    h4 = _files_list_height_px(4)
    assert h4 > h1
    # Cap: many files do not grow without bound
    assert _files_list_height_px(100) == _files_list_height_px(16)
