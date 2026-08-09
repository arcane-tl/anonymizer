"""Windows/options GUI theme helpers (icon path + no display required)."""

from __future__ import annotations

from pathlib import Path

from anonymizer.gui.app import (
    FORMAT_LABELS,
    MODE_LABELS,
    STYLE_LABELS,
    _guess_outputs,
    _label_for,
    _value_for,
    resolve_dialog_icon_path,
)


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
    assert keys == ["md", "source", "both"]


def test_mode_and_style_label_keys():
    assert [k for k, _ in MODE_LABELS] == ["strict", "standard", "extract"]
    assert [k for k, _ in STYLE_LABELS] == ["placeholder", "remove"]
    assert "Strict" in MODE_LABELS[0][1]
    assert "placeholders" in STYLE_LABELS[0][1]


def test_label_value_roundtrip():
    assert _value_for(MODE_LABELS, _label_for(MODE_LABELS, "standard")) == "standard"
    assert _value_for(FORMAT_LABELS, "Source filetype") == "source"


def test_guess_outputs_respects_format(tmp_path: Path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    md = tmp_path / "doc.anonymized.md"
    md.write_text("# x\n", encoding="utf-8")
    native = tmp_path / "doc.anonymized.pdf"
    native.write_bytes(b"%PDF")

    only_md = _guess_outputs([pdf], "strict", "md")
    assert only_md == [str(md)]

    only_src = _guess_outputs([pdf], "strict", "source")
    assert only_src == [str(native)]

    both = _guess_outputs([pdf], "strict", "both")
    assert both == [str(md), str(native)]

    # Extract never returns native even if format says both
    extracted = tmp_path / "doc.md"
    extracted.write_text("t\n", encoding="utf-8")
    extract_outs = _guess_outputs([pdf], "extract", "both")
    assert extract_outs == [str(extracted)]
