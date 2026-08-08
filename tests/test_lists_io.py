"""Shared allow/deny config I/O for GUIs."""

from __future__ import annotations

from pathlib import Path

from anonymizer.lists_io import load_lists, save_lists


def test_save_and_load_lists(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("ANONYMIZER_CONFIG", str(cfg))
    save_lists("Y-tunnus\nFoo\n", "BarCorp\n", path=cfg)
    allow, deny = load_lists(cfg)
    assert "Y-tunnus" in allow
    assert "Foo" in allow
    assert "BarCorp" in deny
    # preserve unknown keys on second save
    cfg.write_text("mode: standard\nallowlist: [A]\ndenylist: []\n", encoding="utf-8")
    save_lists(["A", "B"], [], path=cfg)
    text = cfg.read_text(encoding="utf-8")
    assert "mode: standard" in text or "standard" in text
