"""Machine-readable templates I/O for Mac GUI (shell bridge).

Commands (stdout only; errors on stderr, exit non-zero):

  list                         JSON array of packs
  get ID                       one pack JSON
  save ID --allow-from F --deny-from F
       [--title T | --title-from F]
       [--description D | --description-from F]
  fork ID                      create user fork; print new id
  new [TITLE]                  create empty user pack (default "New template"); print id
  delete ID                    remove user pack file
  set-enabled id1,id2          write templates_enabled to config
  print-enabled                CSV of currently enabled ids
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from anonymizer.anonymize.config import load_config
from anonymizer.anonymize.templates import (
    Template,
    default_enabled_ids,
    deny_from_lines,
    discover_templates,
    fork_template,
    lines_from_text,
    load_template_file,
    persist_templates_enabled,
    resolve_enabled_ids,
    save_template,
    slugify,
)
from anonymizer.lists_io import default_config_path


def _pack_dict(t: Template) -> dict:
    return {
        "id": t.id,
        "title": t.display_title(),
        "description": t.description or "",
        "builtin": bool(t.builtin),
        "default": bool(t.default),
        "allow": list(t.allow),
        "deny": [d.text for d in t.deny if d.text],
        "path": str(t.path) if t.path else "",
    }


def _find(tid: str) -> Template:
    for t in discover_templates():
        if t.id == tid:
            return t
    raise SystemExit(f"error: unknown template id: {tid}")


def cmd_list() -> int:
    packs = discover_templates()
    print(json.dumps([_pack_dict(t) for t in packs], ensure_ascii=False))
    return 0


def cmd_get(tid: str) -> int:
    print(json.dumps(_pack_dict(_find(tid)), ensure_ascii=False))
    return 0


def cmd_save(
    tid: str,
    allow_from: Path,
    deny_from: Path,
    *,
    title: str | None = None,
    description: str | None = None,
    title_from: Path | None = None,
    description_from: Path | None = None,
) -> int:
    t = _find(tid)
    if t.builtin:
        print("error: cannot save builtin pack; fork it first", file=sys.stderr)
        return 2
    allow = lines_from_text(allow_from.read_text(encoding="utf-8"))
    deny = deny_from_lines(lines_from_text(deny_from.read_text(encoding="utf-8")))
    new_title = t.title
    if title_from is not None:
        new_title = title_from.read_text(encoding="utf-8").strip()
    elif title is not None:
        new_title = title.strip()
    if not new_title:
        print("error: title must not be empty", file=sys.stderr)
        return 2
    new_desc = t.description or ""
    if description_from is not None:
        new_desc = description_from.read_text(encoding="utf-8").strip()
    elif description is not None:
        new_desc = description.strip()
    updated = Template(
        id=t.id,
        title=new_title,
        description=new_desc,
        allow=allow,
        deny=deny,
        builtin=False,
        default=t.default,
        path=t.path,
        languages=list(t.languages),
    )
    path = save_template(updated)
    print(str(path))
    return 0


def cmd_fork(tid: str) -> int:
    t = _find(tid)
    forked = fork_template(t)
    # Avoid id clash
    base = forked.id
    n = 2
    known = {p.id for p in discover_templates()}
    while forked.id in known:
        forked = Template(
            id=slugify(f"{base}-{n}"),
            title=forked.title,
            description=forked.description,
            allow=list(forked.allow),
            deny=list(forked.deny),
            builtin=False,
            default=False,
            languages=list(forked.languages),
        )
        n += 1
    save_template(forked)
    print(forked.id)
    return 0


def cmd_new(title: str = "") -> int:
    title = (title or "").strip() or "New template"
    known = {p.id for p in discover_templates()}
    tid = slugify(title)
    if not tid:
        tid = "new-template"
    base = tid
    n = 2
    while tid in known:
        tid = slugify(f"{base}-{n}")
        n += 1
    # Unique display title if "New template" already exists
    display = title
    if any(p.display_title() == display for p in discover_templates()):
        k = 2
        while any(p.display_title() == f"{title} {k}" for p in discover_templates()):
            k += 1
        display = f"{title} {k}"
    t = Template(
        id=tid,
        title=display,
        description="",
        builtin=False,
        default=False,
    )
    save_template(t)
    print(tid)
    return 0


def cmd_delete(tid: str) -> int:
    t = _find(tid)
    if t.builtin:
        print("error: cannot delete builtin pack", file=sys.stderr)
        return 2
    if t.path and t.path.is_file():
        t.path.unlink()
    print("ok")
    return 0


def cmd_set_enabled(csv: str) -> int:
    ids = [x.strip() for x in (csv or "").split(",") if x.strip()]
    known = {p.id for p in discover_templates()}
    ids = [i for i in ids if i in known]
    path = persist_templates_enabled(ids)
    print(str(path))
    return 0


def cmd_print_enabled() -> int:
    packs = discover_templates()
    cfg_path = default_config_path()
    cfg_enabled = None
    if cfg_path.is_file():
        try:
            cfg_enabled = load_config(cfg_path).templates_enabled
        except Exception:  # noqa: BLE001
            cfg_enabled = None
    if cfg_enabled is None:
        ids = default_enabled_ids(packs)
    else:
        ids = resolve_enabled_ids(config_templates=cfg_enabled, all_templates=packs)
    print(",".join(ids))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    cmd = argv[0]
    rest = argv[1:]
    try:
        if cmd == "list":
            return cmd_list()
        if cmd == "get":
            if not rest:
                print("error: get requires ID", file=sys.stderr)
                return 2
            return cmd_get(rest[0])
        if cmd == "save":
            p = argparse.ArgumentParser(prog="templates_io save")
            p.add_argument("id")
            p.add_argument("--allow-from", type=Path, required=True)
            p.add_argument("--deny-from", type=Path, required=True)
            p.add_argument("--title", default=None)
            p.add_argument("--description", default=None)
            p.add_argument("--title-from", type=Path, default=None)
            p.add_argument("--description-from", type=Path, default=None)
            ns = p.parse_args(rest)
            return cmd_save(
                ns.id,
                ns.allow_from,
                ns.deny_from,
                title=ns.title,
                description=ns.description,
                title_from=ns.title_from,
                description_from=ns.description_from,
            )
        if cmd == "fork":
            if not rest:
                print("error: fork requires ID", file=sys.stderr)
                return 2
            return cmd_fork(rest[0])
        if cmd == "new":
            title = " ".join(rest).strip()
            return cmd_new(title)
        if cmd == "delete":
            if not rest:
                print("error: delete requires ID", file=sys.stderr)
                return 2
            return cmd_delete(rest[0])
        if cmd == "set-enabled":
            csv = rest[0] if rest else ""
            return cmd_set_enabled(csv)
        if cmd in {"print-enabled", "enabled"}:
            return cmd_print_enabled()
        print(f"error: unknown command: {cmd}", file=sys.stderr)
        return 2
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        if exc.code:
            print(str(exc.code), file=sys.stderr)
            return 1
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
