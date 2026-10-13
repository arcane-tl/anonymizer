"""Update apply decisions. No network and no Homebrew."""

from __future__ import annotations

from anonymizer.util.update_apply import mac_can_update, mac_manual_steps, windows_manual_steps


def test_mac_can_update_requires_applications_path(monkeypatch) -> None:
    monkeypatch.setattr(
        "anonymizer.util.update_apply.homebrew_cask_installed",
        lambda: True,
    )
    assert mac_can_update("/Applications/Anonymizer.app") is True
    assert mac_can_update("/Users/ttl/Applications/Anonymizer.app") is False


def test_manual_steps_name_the_release() -> None:
    assert "brew uninstall --cask anonymizer-app" in mac_manual_steps()
    assert "Anonymizer-Setup-1.6.0.exe" in windows_manual_steps("1.6.0")
    assert "Settings" in windows_manual_steps("1.6.0")
