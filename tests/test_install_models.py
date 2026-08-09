"""Tests for anonymizer.install_models helpers (no network)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from anonymizer import install_models as im
from anonymizer.install_models import (
    candidates_for,
    check_langs,
    first_loadable,
    model_loadable,
    model_name,
    precheck_langs,
    resolve_wheel_url,
)


def test_model_name_matrix() -> None:
    assert model_name("en", "lg") == "en_core_web_lg"
    assert model_name("fi", "sm") == "fi_core_news_sm"
    assert model_name("sv", "md") == "sv_core_news_md"


def test_candidates_fallback() -> None:
    assert candidates_for("en", "lg", fallback=True) == [
        "en_core_web_lg",
        "en_core_web_md",
        "en_core_web_sm",
    ]
    assert candidates_for("en", "lg", fallback=False) == ["en_core_web_lg"]
    assert candidates_for("fi", "md", fallback=True) == [
        "fi_core_news_md",
        "fi_core_news_sm",
    ]


def test_unknown_lang_raises() -> None:
    with pytest.raises(ValueError, match="Unknown language"):
        model_name("de", "lg")


def test_resolve_wheel_url_shape() -> None:
    pytest.importorskip("spacy")
    url = resolve_wheel_url("en_core_web_sm")
    assert url.startswith("https://github.com/explosion/spacy-models/releases/download/")
    assert url.endswith("-py3-none-any.whl")
    assert "en_core_web_sm-" in url
    # Must include both version dir and wheel file (truncation caused 404s)
    parts = url.split("/")
    assert parts[-1].endswith(".whl")
    assert parts[-2].startswith("en_core_web_sm-")


def test_model_loadable_false_for_garbage() -> None:
    assert model_loadable("this_model_does_not_exist_xyz") is False


def test_check_langs_returns_bools() -> None:
    status = check_langs(["en"], "lg")
    assert "en" in status
    assert isinstance(status["en"], bool)


def test_precheck_short_circuits_without_pip() -> None:
    """If models already load, install_langs must not call pip."""
    with (
        patch.object(im, "model_loadable", side_effect=lambda n: n.endswith("_lg")),
        patch.object(im, "pip_install") as pip,
    ):
        result = im.install_langs(["en", "fi"], "lg", fallback=True, quiet=True)
    assert result["en"] == "en_core_web_lg"
    assert result["fi"] == "fi_core_news_lg"
    pip.assert_not_called()


def test_precheck_langs_maps_packages() -> None:
    with patch.object(
        im, "model_loadable", side_effect=lambda n: n == "en_core_web_sm"
    ):
        pre = precheck_langs(["en"], "lg", fallback=True)
        assert pre["en"] == "en_core_web_sm"
        assert first_loadable("en", "lg", fallback=True) == "en_core_web_sm"


def test_main_exits_zero_when_precheck_ok(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(im, "model_loadable", return_value=True):
        code = im.main(["--langs", "en,fi", "--size", "lg"])
    assert code == 0
    out = capsys.readouterr().out
    assert "already ready" in out
