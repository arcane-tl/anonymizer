"""Load/save allowlist & denylist for GUI helpers (Mac shell + Windows GUI).

User config path: ~/.config/anonymizer/config.yaml
(override with ANONYMIZER_CONFIG). Merges list keys only; preserves others.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from anonymizer.anonymize.config import DEFAULT_ALLOWLIST, DenylistEntry, load_config


def default_config_path() -> Path:
    override = os.environ.get("ANONYMIZER_CONFIG")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "anonymizer" / "config.yaml"
    return Path.home() / ".config" / "anonymizer" / "config.yaml"


def load_lists(path: Path | None = None) -> tuple[list[str], list[str]]:
    """Return (allow_lines, deny_lines).

    Defaults apply only when **no config file** exists. An explicit empty
    ``allowlist: []`` in YAML is preserved (does not restore defaults).
    """
    cfg_path = path or default_config_path()
    if cfg_path.is_file():
        cfg = load_config(cfg_path)
        allow = list(cfg.allowlist)
    else:
        cfg = load_config(None)
        allow = list(DEFAULT_ALLOWLIST)
    deny = [e.text for e in cfg.denylist if e.text]
    return allow, deny


def save_lists(
    allow: list[str] | str,
    deny: list[str] | str,
    path: Path | None = None,
) -> Path:
    """Write allow/deny into config YAML; preserve other keys. Returns path."""
    cfg_path = path or default_config_path()

    def _lines(src: list[str] | str) -> list[str]:
        if isinstance(src, str):
            raw_lines = src.splitlines()
        else:
            raw_lines = list(src)
        out: list[str] = []
        for raw in raw_lines:
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            out.append(s)
        return out

    allow_lines = _lines(allow)
    deny_lines = _lines(deny)

    data: dict = {}
    if cfg_path.is_file():
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data = raw

    data["allowlist"] = allow_lines
    data["denylist"] = [{"text": t, "entity_type": "ORG"} for t in deny_lines]

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    try:
        cfg_path.chmod(0o600)
    except OSError:
        pass
    load_config(cfg_path)  # validate
    return cfg_path


def format_print_sections(allow: list[str], deny: list[str]) -> str:
    """Mac lists-io.sh compatible text."""
    parts = ["---ALLOW---", *allow, "---DENY---", *deny]
    return "\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI: print | save --allow-from F --deny-from F"""
    import argparse

    p = argparse.ArgumentParser(prog="anonymizer-lists")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("print", help="Print ---ALLOW--- / ---DENY--- sections")
    sp = sub.add_parser("save", help="Save lists into config YAML")
    sp.add_argument("--allow-from", required=True)
    sp.add_argument("--deny-from", required=True)
    args = p.parse_args(argv)

    if args.cmd == "print":
        allow, deny = load_lists()
        print(format_print_sections(allow, deny), end="")
        return 0
    allow_text = Path(args.allow_from).read_text(encoding="utf-8")
    deny_text = Path(args.deny_from).read_text(encoding="utf-8")
    out = save_lists(allow_text, deny_text)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
