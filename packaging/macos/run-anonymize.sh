#!/usr/bin/env bash
# run-anonymize.sh — Resolve the anonymize CLI and process one or more files.
#
# Usage:
#   run-anonymize.sh [--review] [mode] file [file ...]
#   mode: strict | standard | extract   (default: strict)
#
# On success, prints one line per written Markdown file to stdout:
#   OUTPUT:/absolute/path/to/file.md
# (so the Mac droplet can offer to open them)
#
# --review needs an interactive terminal (checkbox UI). Use Terminal.app
# for that path; plain do shell script has no TTY.
#
# PATH resolution (first hit wins):
#   1. $ANONYMIZER_BIN
#   2. $HOME/.local/bin/anonymize
#   3. command -v anonymize

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run-anonymize.sh [--review] [mode] file [file ...]

  --review   Interactive redaction review (requires a real terminal)
  mode       strict (default) | standard | extract
  file       PDF, DOCX, or text path(s)

Stdout (success): one OUTPUT:/abs/path line per written Markdown file.

Environment:
  ANONYMIZER_BIN   Absolute path to the anonymize executable
  ANONYMIZER_OPEN  If set to 1/y/yes, open output files after success (TTY only)
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

# Mirror anonymizer.util.files.default_output_path (default next to source).
expected_output_path() {
  local input_path="$1"
  local mode="$2"
  local dir base stem name in_abs out_abs
  dir=$(cd "$(dirname -- "$input_path")" && pwd)
  base=$(basename -- "$input_path")
  if [[ "$base" == *.* ]]; then
    stem="${base%.*}"
  else
    stem="$base"
  fi

  if [[ "$mode" == "extract" ]]; then
    name="${stem}.md"
    in_abs="${dir}/${base}"
    out_abs="${dir}/${name}"
    # Never overwrite a .md source in extract mode
    if [[ "$in_abs" == "$out_abs" ]]; then
      name="${stem}.extracted.md"
    fi
  else
    name="${stem}.anonymized.md"
  fi
  printf '%s/%s\n' "$dir" "$name"
}

REVIEW=0
if [[ $# -ge 1 && "$1" == "--review" ]]; then
  REVIEW=1
  shift
fi

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

if [[ "$REVIEW" -eq 1 && "$MODE" == "extract" ]]; then
  echo "error: --review is not used in extract mode (nothing to redaction-review)" >&2
  exit 2
fi

if [[ "$REVIEW" -eq 1 && ! -t 0 ]]; then
  echo "error: --review needs an interactive terminal (open via Terminal.app)." >&2
  exit 2
fi

BIN="$(find_anonymize)" || exit 2

ok=0
fail=0
outputs=()

for f in "$@"; do
  if [[ ! -e "$f" ]]; then
    echo "error: path not found: $f" >&2
    fail=$((fail + 1))
    continue
  fi
  # Prefer absolute input path for stable default output location
  if command -v realpath >/dev/null 2>&1; then
    f_abs=$(realpath "$f")
  else
    f_abs=$(cd "$(dirname -- "$f")" && pwd)/$(basename -- "$f")
  fi

  if [[ "$REVIEW" -eq 1 ]]; then
    # Real TTY: show progress + checkbox review (no --quiet)
    if "$BIN" "$MODE" "$f_abs" --review; then
      out_path=$(expected_output_path "$f_abs" "$MODE")
      if [[ -f "$out_path" ]]; then
        printf 'OUTPUT:%s\n' "$out_path"
        outputs+=("$out_path")
      fi
      ok=$((ok + 1))
    else
      echo "error: anonymize failed for: $f_abs" >&2
      fail=$((fail + 1))
    fi
  else
    if "$BIN" "$MODE" "$f_abs" --quiet; then
      out_path=$(expected_output_path "$f_abs" "$MODE")
      if [[ -f "$out_path" ]]; then
        printf 'OUTPUT:%s\n' "$out_path"
        outputs+=("$out_path")
      else
        echo "warning: expected output missing: $out_path" >&2
      fi
      ok=$((ok + 1))
    else
      echo "error: anonymize failed for: $f_abs" >&2
      fail=$((fail + 1))
    fi
  fi
done

if [[ "$fail" -gt 0 ]]; then
  echo "done: $ok ok, $fail failed (mode=$MODE)" >&2
  exit 1
fi
echo "done: $ok file(s) ok (mode=$MODE)" >&2

# Open policy (droplet sets this up front so we never ask twice):
#   ANONYMIZER_OPEN=1|y|yes  → open outputs, no prompt
#   ANONYMIZER_OPEN=0|n|no   → never open, no prompt
#   unset + --review + TTY   → prompt once (CLI / Terminal without droplet)
want_open="${ANONYMIZER_OPEN:-}"
if [[ ${#outputs[@]} -gt 0 ]]; then
  case "$(printf '%s' "$want_open" | tr '[:upper:]' '[:lower:]')" in
    1|y|yes)
      if command -v open >/dev/null 2>&1; then
        open "${outputs[@]}"
      fi
      ;;
    0|n|no|"")
      if [[ -z "$want_open" && "$REVIEW" -eq 1 && -t 0 ]]; then
        printf 'Open anonymized file(s) in the default app? [y/N] ' >&2
        read -r ans || ans=""
        case "$(printf '%s' "$ans" | tr '[:upper:]' '[:lower:]')" in
          y|yes)
            if command -v open >/dev/null 2>&1; then
              open "${outputs[@]}"
            fi
            ;;
        esac
      fi
      ;;
  esac
fi

exit 0
