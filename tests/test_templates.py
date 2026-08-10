"""Allow/deny templates (use-case packs)."""

from __future__ import annotations

from pathlib import Path

import yaml

from anonymizer.anonymize.config import AnonymizerConfig, DenylistEntry, load_config
from anonymizer.anonymize.review import ReviewFinding, ReviewSession
from anonymizer.anonymize.templates import (
    apply_templates_to_config,
    default_enabled_ids,
    discover_templates,
    load_template_file,
    merge_into_template,
    resolve_enabled_ids,
    save_template,
    session_to_teach_lists,
    teach_template,
    union_templates,
    Template,
)


def test_discover_builtins():
    packs = discover_templates(include_user=False)
    ids = {t.id for t in packs}
    assert "fi-field-labels" in ids
    assert "en-field-labels" in ids
    assert "en-legal-boilerplate" in ids
    assert all(t.builtin for t in packs)
    defaults = default_enabled_ids(packs)
    assert "fi-field-labels" in defaults
    assert "en-legal-boilerplate" in defaults


def test_union_allow_wins_conflict():
    packs = [
        Template(id="a", allow=["Acme"], deny=[DenylistEntry("Other", "ORG")]),
        Template(
            id="b",
            allow=[],
            deny=[DenylistEntry("Acme", "ORG"), DenylistEntry("Beta", "ORG")],
        ),
    ]
    m = union_templates(packs, ["a", "b"])
    assert "Acme" in m.allow
    deny_texts = {d.text for d in m.deny}
    assert "Acme" not in deny_texts
    assert "Beta" in deny_texts
    assert "Acme" in m.conflicts


def test_apply_templates_replaces_default_allowlist():
    cfg = AnonymizerConfig()
    # Defaults currently include Y-tunnus via DEFAULT_ALLOWLIST
    assert any(a.casefold() == "y-tunnus" for a in cfg.allowlist)
    packs = discover_templates(include_user=False)
    # Only EN legal boilerplate — should not include Y-tunnus
    enabled = ["en-legal-boilerplate"]
    apply_templates_to_config(cfg, enabled_ids=enabled, replace_lists=True)
    assert "Force Majeure" in cfg.allowlist
    assert not any(a.casefold() == "y-tunnus" for a in cfg.allowlist)


def test_resolve_cli_overrides_config():
    packs = discover_templates(include_user=False)
    ids = resolve_enabled_ids(
        cli_templates="en-legal-boilerplate",
        config_templates=["fi-field-labels"],
        all_templates=packs,
    )
    assert ids == ["en-legal-boilerplate"]
    # Explicit empty
    ids2 = resolve_enabled_ids(
        cli_templates="",
        config_templates=["fi-field-labels"],
        all_templates=packs,
    )
    assert ids2 == []


def test_save_and_load_user_template(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANONYMIZER_TEMPLATES", str(tmp_path))
    t = Template(
        id="my-company",
        title="My company",
        allow=["Internal Product X"],
        deny=[DenylistEntry("Secret Partner Oy", "ORG")],
    )
    path = save_template(t)
    assert path.is_file()
    loaded = load_template_file(path)
    assert loaded.id == "my-company"
    assert "Internal Product X" in loaded.allow
    assert loaded.deny[0].text == "Secret Partner Oy"


def test_teach_template_from_session(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANONYMIZER_TEMPLATES", str(tmp_path))
    session = ReviewSession(
        original_blocks=["Hello Internal Widget and Acme Hidden Oy"],
        findings=[
            ReviewFinding(
                placeholder="[ORG_1]",
                original="Internal Widget",
                entity_type="ORG",
                enabled=False,  # keep clear
            ),
            ReviewFinding(
                placeholder="[ORG_2]",
                original="Acme Hidden Oy",
                entity_type="ORG",
                enabled=True,
                source="user",
            ),
        ],
    )
    path = teach_template("my-learn", session, create_title="My learn pack")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "Internal Widget" in data["allow"]
    deny_texts = [d["text"] if isinstance(d, dict) else d for d in data["deny"]]
    assert "Acme Hidden Oy" in deny_texts


def test_session_to_teach_lists():
    session = ReviewSession(
        original_blocks=["x"],
        findings=[
            ReviewFinding(
                placeholder="[PERSON_1]",
                original="Keep Me",
                entity_type="PERSON",
                enabled=False,
            ),
        ],
    )
    allow, deny = session_to_teach_lists(session)
    assert allow == ["Keep Me"]
    assert deny == []


def test_merge_into_template_skips_dupes():
    t = Template(id="x", allow=["Foo"], deny=[DenylistEntry("Bar", "ORG")])
    t2 = merge_into_template(
        t,
        allow_add=["foo", "Baz"],  # foo dupe casefold
        deny_add=["Bar", "Qux"],
    )
    assert t2.allow == ["Foo", "Baz"]
    assert {d.text for d in t2.deny} == {"Bar", "Qux"}


def test_config_templates_enabled(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "templates_enabled:\n  - en-legal-boilerplate\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.templates_enabled == ["en-legal-boilerplate"]
