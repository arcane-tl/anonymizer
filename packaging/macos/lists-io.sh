#!/usr/bin/env bash
# lists-io.sh — Load/save legacy allowlist & denylist (config.yaml).
#
# Optional CLI helper around: python -m anonymizer.lists_io
# Not bundled in Anonymizer.app (Templates UI uses templates-io.sh).
# User config: ~/.config/anonymizer/config.yaml (ANONYMIZER_CONFIG override)
#
# Usage:
#   lists-io.sh print
#   lists-io.sh save --allow-from FILE --deny-from FILE

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
    # Strip env from shebang like "#!/usr/bin/env python"
    if [[ "$py" == *"/env "* ]]; then
      py="${py##* }"
    fi
    if "$py" -c "import anonymizer.lists_io" 2>/dev/null; then
      printf '%s\n' "$py"
      return 0
    fi
  done
  echo "error: no Python with anonymizer installed (install CLI first)" >&2
  return 2
}

py=$(find_python) || exit 2
mkdir -p "$(dirname "$ANONYMIZER_CONFIG")"
exec "$py" -m anonymizer.lists_io "$@"
