"""Windows/options GUI theme helpers (icon path + no display required)."""

from __future__ import annotations

from pathlib import Path

from anonymizer.gui.app import resolve_dialog_icon_path


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
