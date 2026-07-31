#!/usr/bin/env bash
# run-anonymize.sh — Resolve the anonymize CLI and process one or more files.
#
# Usage:
#   run-anonymize.sh [mode] file [file ...]
#   mode: strict | standard | extract   (default: strict)
#
# PATH resolution (first hit wins):
#   1. $ANONYMIZER_BIN
#   2. $HOME/.local/bin/anonymize
#   3. command -v anonymize
#
# Exit codes:
#   0  all files processed successfully
#   1  anonymize failed for one or more files
#   2  usage / missing CLI / bad mode / no input files

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run-anonymize.sh [mode] file [file ...]

  mode   strict (default) | standard | extract
  file   PDF, DOCX, or text path(s)

Environment:
  ANONYMIZER_BIN   Absolute path to the anonymize executable
EOF
}

find_anonymize() {
  if [[ -n "${ANONYMIZER_BIN:-}" ]]; then
    if [[ -x "$ANONYMIZER_BIN" ]]; then
      printf '%s\n' "$ANONYMIZER_BIN"
      return 0
    fi
    echo "error: ANONYMIZER_BIN is set but not executable: $ANONYMIZER_BIN" >&2
    return 2
  fi
  local candidate="$HOME/.local/bin/anonymize"
  if [[ -x "$candidate" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi
  if command -v anonymize >/dev/null 2>&1; then
    command -v anonymize
    return 0
  fi
  cat >&2 <<'EOF'
error: could not find the anonymize CLI.

Install the tool first, then try again:
  curl -fsSL https://raw.githubusercontent.com/arcane-tl/anonymizer/main/scripts/install.sh | bash -s -- --yes
  anonymize doctor

Or set ANONYMIZER_BIN to the full path of the anonymize executable.
EOF
  return 2
}

normalize_mode() {
  local raw
  raw=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
  case "$raw" in
    strict|scrub|full) echo strict ;;
    standard|normal|pii) echo standard ;;
    extract|text|plain) echo extract ;;
    *)
      echo "error: unknown mode '$1' (use strict, standard, or extract)" >&2
      return 2
      ;;
  esac
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

MODE="strict"
FIRST="$1"
case "$(printf '%s' "$FIRST" | tr '[:upper:]' '[:lower:]')" in
  strict|scrub|full|standard|normal|pii|extract|text|plain)
    MODE="$(normalize_mode "$FIRST")" || exit 2
    shift
    ;;
esac

if [[ $# -lt 1 ]]; then
  echo "error: no input files" >&2
  usage >&2
  exit 2
fi

BIN="$(find_anonymize)" || exit 2

ok=0
fail=0
for f in "$@"; do
  if [[ ! -e "$f" ]]; then
    echo "error: path not found: $f" >&2
    fail=$((fail + 1))
    continue
  fi
  # Real CLI entry: verb form  anonymize extract|standard|strict FILE
  if "$BIN" "$MODE" "$f" --quiet; then
    ok=$((ok + 1))
  else
    echo "error: anonymize failed for: $f" >&2
    fail=$((fail + 1))
  fi
done

if [[ "$fail" -gt 0 ]]; then
  echo "done: $ok ok, $fail failed (mode=$MODE)" >&2
  exit 1
fi
echo "done: $ok file(s) ok (mode=$MODE)" >&2
exit 0
