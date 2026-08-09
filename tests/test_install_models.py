"""Tests for anonymizer.install_models helpers (no network)."""

from __future__ import annotations

import pytest

from anonymizer.install_models import (
    candidates_for,
    check_langs,
    model_loadable,
    model_name,
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
