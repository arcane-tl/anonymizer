#!/usr/bin/env bash
# templates-io.sh — Machine-readable templates for the Mac GUI.
#
# Thin wrapper around: python -m anonymizer.templates_io
#
# Usage:
#   templates-io.sh list
#   templates-io.sh get ID
#   templates-io.sh save ID --allow-from F --deny-from F
#   templates-io.sh fork ID
#   templates-io.sh new "Title"
#   templates-io.sh delete ID
#   templates-io.sh set-enabled id1,id2
#   templates-io.sh print-enabled

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/anonymizer"
export ANONYMIZER_CONFIG="${ANONYMIZER_CONFIG:-$CONFIG_DIR/config.yaml}"

find_python() {
  local candidates=()
  if [[ -n "${ANONYMIZER_BIN:-}" && -x "${ANONYMIZER_BIN}" ]]; then
    local shebang
    shebang=$(head -1 "$ANONYMIZER_BIN" 2>/dev/null || true)
    if [[ "$shebang" == "#!"* ]]; then
      candidates+=("${shebang#\#!}")
    fi
  fi
  if command -v anonymize >/dev/null 2>&1; then
    local anon
    anon=$(command -v anonymize)
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
  [[ -x "$HERE/../../.venv/bin/python" ]] && candidates+=("$HERE/../../.venv/bin/python")
  candidates+=(python3 python)

  local py
  for py in "${candidates[@]}"; do
    [[ -z "$py" ]] && continue
    if [[ "$py" == *"/env "* ]]; then
      py="${py##* }"
    fi
    if "$py" -c "import anonymizer.templates_io" 2>/dev/null; then
      printf '%s\n' "$py"
      return 0
    fi
  done
  echo "error: no Python with anonymizer installed (install CLI first)" >&2
  return 2
}

py=$(find_python) || exit 2
mkdir -p "$(dirname "$ANONYMIZER_CONFIG")"
exec "$py" -m anonymizer.templates_io "$@"
