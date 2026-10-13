"""Update-check version compare and mocked GitHub fetch. No network, no Tk."""

from __future__ import annotations

import json
from email.message import EmailMessage
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from anonymizer.util.update_check import (
    ENV_DISABLE,
    ENV_OVERRIDE,
    MAX_BODY_BYTES,
    RELEASES_LATEST_URL,
    TIMEOUT_SECONDS,
    UpdateNotice,
    check_for_update,
    fetch_latest_payload,
    is_newer_stable,
    main,
    notice_from_payload,
    parse_stable_version,
)

_CURRENT = "1.5.1"
_NEWER_URL = "https://github.com/arcane-tl/anonymizer/releases/tag/v9.9.9"
_NEWER_OVERRIDE = json.dumps({"tag_name": "v9.9.9", "html_url": _NEWER_URL})


@pytest.mark.parametrize(
    ("remote", "current", "newer"),
    [
        ("v1.5.2", "1.5.1", True),
        ("V1.6.0", "1.5.9", True),
        ("v2.0.0", "1.9.9", True),
        ("v1.10.0", "1.9.0", True),
        ("v1.5.1", "1.5.1", False),
        ("v1.5.0", "1.5.1", False),
        ("  v1.4.0  ", "1.0.0", True),
        ("v1.5.1-rc.1", "1.5.0", False),
        ("1.5.1a1", "1.5.0", False),
        ("1.5.1+dev", "1.5.0", False),
        ("v9.9.9", "0.0.0+dev", False),
        ("v1.5.2", "1.5.1-rc.1", False),
        ("1.5", "1.0.0", False),
        ("1.5.1.1", "1.5.1", False),
        ("", "1.5.1", False),
        ("not-a-version", "1.5.1", False),
    ],
)
def test_is_newer_stable(remote: str, current: str, newer: bool) -> None:
    assert is_newer_stable(remote, current) is newer


def test_parse_stable_version() -> None:
    assert parse_stable_version("v1.5.2") == (1, 5, 2)
    assert parse_stable_version("1.05.0") == (1, 5, 0)
    assert parse_stable_version("1.5.1-rc.1") is None
    assert parse_stable_version("1.5.1a1") is None
    assert parse_stable_version("1.5.1.dev0") is None
    assert parse_stable_version("") is None


def test_notice_from_payload_newer() -> None:
    notice = notice_from_payload(
        {"tag_name": "v9.9.9", "html_url": _NEWER_URL, "body": "ignored"},
        _CURRENT,
    )
    assert notice == UpdateNotice("9.9.9", _NEWER_URL)


def test_notice_from_payload_not_newer() -> None:
    assert notice_from_payload(
        {"tag_name": "v1.5.1", "html_url": _NEWER_URL},
        _CURRENT,
    ) is None
    assert notice_from_payload(
        {"tag_name": "v1.0.0", "html_url": _NEWER_URL},
        _CURRENT,
    ) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"html_url": _NEWER_URL},
        {"tag_name": "v9.9.9"},
        {"tag_name": 999, "html_url": _NEWER_URL},
        {"tag_name": "v9.9.9", "html_url": 12},
        ["v9.9.9", _NEWER_URL],
        "v9.9.9",
        None,
        {"tag_name": "v9.9.9", "html_url": "javascript:alert(1)"},
        {"tag_name": "v9.9.9", "html_url": "file:///tmp/release"},
        {"tag_name": "v9.9.9", "html_url": "https://"},
        {"tag_name": "v9.9.9", "html_url": "https://example.com/a b"},
    ],
)
def test_notice_from_payload_rejects(payload: object) -> None:
    assert notice_from_payload(payload, _CURRENT) is None


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            return self._data
        return self._data[:n]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


def _release_bytes(tag: str = "v9.9.9", url: str = _NEWER_URL) -> bytes:
    return json.dumps(
        {"tag_name": tag, "html_url": url, "body": "release notes"}
    ).encode("utf-8")


def test_fetch_latest_payload_success() -> None:
    captured: dict[str, object] = {}

    def _open(req: object, timeout: float | None = None) -> _FakeResponse:
        captured["req"] = req
        captured["timeout"] = timeout
        return _FakeResponse(_release_bytes())

    with patch("urllib.request.urlopen", side_effect=_open):
        payload = fetch_latest_payload()

    assert payload is not None
    assert payload["tag_name"] == "v9.9.9"
    assert payload["html_url"] == _NEWER_URL
    req = captured["req"]
    assert req.get_full_url() == RELEASES_LATEST_URL  # type: ignore[attr-defined]
    assert captured["timeout"] == TIMEOUT_SECONDS
    assert req.get_header("User-agent") == "anonymizer-update-check"  # type: ignore[attr-defined]
    assert req.get_header("Accept") == "application/vnd.github+json"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "exc",
    [
        HTTPError(RELEASES_LATEST_URL, 403, "Forbidden", EmailMessage(), None),
        URLError("offline"),
        TimeoutError("timed out"),
    ],
)
def test_fetch_latest_payload_errors(exc: Exception) -> None:
    with patch("urllib.request.urlopen", side_effect=exc):
        assert fetch_latest_payload() is None


def test_fetch_latest_payload_bad_json() -> None:
    with patch("urllib.request.urlopen", return_value=_FakeResponse(b"{")):
        assert fetch_latest_payload() is None


def test_fetch_latest_payload_json_list() -> None:
    with patch("urllib.request.urlopen", return_value=_FakeResponse(b"[1, 2]")):
        assert fetch_latest_payload() is None


def test_fetch_latest_payload_body_too_large() -> None:
    blob = b"{" * (MAX_BODY_BYTES + 1)
    with patch("urllib.request.urlopen", return_value=_FakeResponse(blob)):
        assert fetch_latest_payload() is None


def _forbid_network() -> object:
    return patch("urllib.request.urlopen", side_effect=AssertionError("no network"))


def test_check_for_update_override_skips_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_OVERRIDE, _NEWER_OVERRIDE)
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    with _forbid_network() as opened:
        notice = check_for_update(_CURRENT)
    opened.assert_not_called()
    assert notice == UpdateNotice("9.9.9", _NEWER_URL)


def test_check_for_update_override_older(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        ENV_OVERRIDE,
        json.dumps({"tag_name": "v1.0.0", "html_url": _NEWER_URL}),
    )
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    with _forbid_network() as opened:
        assert check_for_update(_CURRENT) is None
    opened.assert_not_called()


def test_check_for_update_override_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_OVERRIDE, "{")
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    with _forbid_network() as opened:
        assert check_for_update(_CURRENT) is None
    opened.assert_not_called()


@pytest.mark.parametrize("flag", ["1", "true", "yes", "on"])
def test_check_for_update_disabled(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    monkeypatch.setenv(ENV_DISABLE, flag)
    monkeypatch.setenv(ENV_OVERRIDE, _NEWER_OVERRIDE)
    with _forbid_network() as opened:
        assert check_for_update(_CURRENT) is None
    opened.assert_not_called()


def test_check_for_update_fetches_newer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_OVERRIDE, raising=False)
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    with patch("urllib.request.urlopen", return_value=_FakeResponse(_release_bytes())):
        notice = check_for_update(_CURRENT)
    assert notice == UpdateNotice("9.9.9", _NEWER_URL)


def test_check_for_update_fetches_older(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_OVERRIDE, raising=False)
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    body = _release_bytes(tag="v1.0.0", url=_NEWER_URL)
    with patch("urllib.request.urlopen", return_value=_FakeResponse(body)):
        assert check_for_update(_CURRENT) is None


def test_main_prints_notice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(ENV_OVERRIDE, _NEWER_OVERRIDE)
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    assert main([]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload == {"version": "9.9.9", "html_url": _NEWER_URL}
    assert captured.err == ""


def test_main_disable_prints_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(ENV_DISABLE, "1")
    monkeypatch.setenv(ENV_OVERRIDE, _NEWER_OVERRIDE)
    assert main(None) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
