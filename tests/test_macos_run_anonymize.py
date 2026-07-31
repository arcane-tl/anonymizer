"""Tests for packaging/macos/run-anonymize.sh (Mac GUI helper)."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "packaging" / "macos" / "run-anonymize.sh"


def _anonymize_bin() -> str | None:
    return shutil.which("anonymize")


@pytest.fixture
def script_env(monkeypatch):
    """Ensure the real CLI is discoverable via ANONYMIZER_BIN."""
    bin_path = _anonymize_bin()
    if not bin_path:
        pytest.skip("anonymize CLI not on PATH")
    env = os.environ.copy()
    env["ANONYMIZER_BIN"] = bin_path
    return env


def test_script_exists_and_executable():
    assert SCRIPT.is_file()
    # May not be +x in all checkouts; install-app chmod's the bundled copy
    assert SCRIPT.read_text(encoding="utf-8").startswith("#!/")


def test_run_anonymize_extract_writes_markdown(tmp_path: Path, script_env: dict):
    src = tmp_path / "note.txt"
    src.write_text("Hello from Mac GUI helper.\n", encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(SCRIPT), "extract", str(src)],
        capture_output=True,
        text=True,
        env=script_env,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = tmp_path / "note.md"
    assert out.is_file(), list(tmp_path.iterdir())
    body = out.read_text(encoding="utf-8")
    assert "Hello from Mac GUI helper" in body


def test_run_anonymize_default_mode_is_strict_verb(tmp_path: Path, script_env: dict):
    """Default mode should invoke CLI as 'strict' (or bare strict scrub)."""
    src = tmp_path / "pii.txt"
    src.write_text("Contact alice@example.com please.\n", encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(SCRIPT), str(src)],
        capture_output=True,
        text=True,
        env=script_env,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = tmp_path / "pii.anonymized.md"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "alice@example.com" not in text
    assert "[EMAIL_" in text or "EMAIL" in text


def test_run_anonymize_missing_cli_errors(tmp_path: Path, monkeypatch):
    env = os.environ.copy()
    env["ANONYMIZER_BIN"] = str(tmp_path / "no-such-anonymize")
    env["PATH"] = "/usr/bin:/bin"  # avoid finding a real anonymize
    # Unset home local bin by using empty HOME without .local/bin/anonymize
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env["HOME"] = str(fake_home)
    src = tmp_path / "x.txt"
    src.write_text("x\n", encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(SCRIPT), "extract", str(src)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 2
    assert "could not find" in (proc.stderr + proc.stdout).lower() or "not executable" in (
        proc.stderr + proc.stdout
    ).lower()


def test_run_anonymize_mode_without_files_errors(tmp_path: Path, script_env: dict):
    proc = subprocess.run(
        ["bash", str(SCRIPT), "strict"],
        capture_output=True,
        text=True,
        env=script_env,
    )
    assert proc.returncode == 2
    assert "no input files" in (proc.stderr + proc.stdout).lower()


def test_run_anonymize_text_alias_is_extract(tmp_path: Path, script_env: dict):
    src = tmp_path / "x.txt"
    src.write_text("x\n", encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(SCRIPT), "text", str(src)],
        capture_output=True,
        text=True,
        env=script_env,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "x.md").is_file()
