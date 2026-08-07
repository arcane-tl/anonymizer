#!/usr/bin/env bash
# lists-io.sh — Load/save allowlist & denylist for the Mac GUI.
#
# User config path: ~/.config/anonymizer/config.yaml
# Merges allowlist/denylist only; preserves other YAML keys on save.
#
# Usage:
#   lists-io.sh print
#       Print:
#         ---ALLOW---
#         line...
#         ---DENY---
#         line...
#   lists-io.sh save --allow-from FILE --deny-from FILE
#       Merge lists into ~/.config/anonymizer/config.yaml

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/anonymizer"
CONFIG_PATH="${ANONYMIZER_CONFIG:-$CONFIG_DIR/config.yaml}"

find_python() {
  # Prefer an interpreter that can import anonymizer (same install as CLI).
  local candidates=()
  if [[ -n "${ANONYMIZER_BIN:-}" && -x "${ANONYMIZER_BIN}" ]]; then
    # console_script shebang → first line #!/path/python
    local shebang
    shebang=$(head -1 "$ANONYMIZER_BIN" 2>/dev/null || true)
    if [[ "$shebang" == "#!"* ]]; then
      candidates+=("${shebang#\#!}")
    fi
  fi
  if command -v anonymize >/dev/null 2>&1; then
    local anon
    anon=$(command -v anonymize)
    # Resolve symlink (e.g. ~/.local/bin/anonymize → venv)
    [[ -L "$anon" ]] && anon=$(readlink "$anon" 2>/dev/null || echo "$anon")
    local shebang
    shebang=$(head -1 "$anon" 2>/dev/null || true)
    if [[ "$shebang" == "#!"* ]]; then
      candidates+=("${shebang#\#!}")
    fi
  fi
  [[ -x "$HOME/.local/bin/anonymize" ]] && {
    local a="$HOME/.local/bin/anonymize"
    [[ -L "$a" ]] && a=$(readlink "$a" 2>/dev/null || echo "$a")
    shebang=$(head -1 "$a" 2>/dev/null || true)
    [[ "$shebang" == "#!"* ]] && candidates+=("${shebang#\#!}")
  }
  # Project venv relative to this script (dev)
  [[ -x "$HERE/../../.venv/bin/python" ]] && candidates+=("$HERE/../../.venv/bin/python")
  candidates+=(python3 python)

  local py
  for py in "${candidates[@]}"; do
    [[ -z "$py" ]] && continue
    if "$py" -c "import anonymizer" 2>/dev/null; then
      printf '%s\n' "$py"
      return 0
    fi
  done
  echo "error: no Python with anonymizer installed (install CLI first)" >&2
  return 2
}

cmd_print() {
  local py
  py=$(find_python) || exit 2
  CONFIG_PATH="$CONFIG_PATH" "$py" - <<'PY'
from __future__ import annotations

import os
from pathlib import Path

from anonymizer.anonymize.config import DEFAULT_ALLOWLIST, load_config

path = Path(os.environ["CONFIG_PATH"]).expanduser()
if path.is_file():
    cfg = load_config(path)
else:
    cfg = load_config(None)

print("---ALLOW---")
for line in cfg.allowlist:
    print(line)
print("---DENY---")
for entry in cfg.denylist:
    print(entry.text)
PY
}

cmd_save() {
  local allow_from="" deny_from=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --allow-from) allow_from="${2:-}"; shift 2 ;;
      --deny-from) deny_from="${2:-}"; shift 2 ;;
      *) echo "error: unknown arg: $1" >&2; exit 2 ;;
    esac
  done
  if [[ -z "$allow_from" || -z "$deny_from" ]]; then
    echo "error: save requires --allow-from and --deny-from" >&2
    exit 2
  fi
  if [[ ! -f "$allow_from" || ! -f "$deny_from" ]]; then
    echo "error: allow/deny files not found" >&2
    exit 2
  fi

  mkdir -p "$CONFIG_DIR"
  local py
  py=$(find_python) || exit 2
  CONFIG_PATH="$CONFIG_PATH" ALLOW_FROM="$allow_from" DENY_FROM="$deny_from" "$py" - <<'PY'
from __future__ import annotations

import os
from pathlib import Path

import yaml

from anonymizer.anonymize.config import DenylistEntry, load_config

path = Path(os.environ["CONFIG_PATH"]).expanduser()
allow_path = Path(os.environ["ALLOW_FROM"])
deny_path = Path(os.environ["DENY_FROM"])

def lines(p: Path) -> list[str]:
    out: list[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out

allow = lines(allow_path)
deny_texts = lines(deny_path)

# Start from existing file as raw dict so we keep unknown keys
data: dict = {}
if path.is_file():
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        data = raw

data["allowlist"] = allow
data["denylist"] = [{"text": t, "entity_type": "ORG"} for t in deny_texts]

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(
    yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
    encoding="utf-8",
)
# Validate loadable
load_config(path)
print(path)
PY
}

case "${1:-}" in
  print) cmd_print ;;
  save) shift; cmd_save "$@" ;;
  -h|--help|"")
    sed -n '1,20p' "$0"
    exit 0
    ;;
  *)
    echo "error: unknown command: $1 (use print|save)" >&2
    exit 2
    ;;
esac
