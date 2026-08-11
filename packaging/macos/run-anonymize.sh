#!/usr/bin/env bash
# run-anonymize.sh — Resolve the anonymize CLI and process one or more files.
#
# Usage:
#   run-anonymize.sh [options] [mode] file [file ...]
#   mode: strict | standard | extract   (default: strict)
#
# Options:
#   --review              Document review window (via --review-window on the CLI)
#   --redact-style STYLE  placeholder (default) | remove
#   --format FMT          md (default) | source | both (source = redacted PDF/DOCX)
#   --config PATH         YAML config
#   --template IDS        Comma-separated template ids → CLI --template
#   --learn-to ID         After review, teach pack (CLI --learn-to)
#   --templates-ui        Open Templates dialog; print ENABLED:id1,id2 (or CANCEL)
#   --enabled IDS         Initial enabled ids for --templates-ui
#   --out PATH            Write ENABLED/CANCEL line to PATH (Mac AppleScript)
#   --allow-from PATH     Legacy allowlist lines → temp config merge
#   --deny-from PATH      Legacy denylist lines → temp config merge
#   --out-dir PATH        Write outputs under PATH (CLI --out-dir)
#
# On success, prints one line per written output file to stdout:
#   OUTPUT:/absolute/path/to/file.md
#   OUTPUT:/absolute/path/to/file.anonymized.pdf   (when --format both|source)
#
# --review opens the document review window (--review-window). Prefer
# Terminal.app / a desktop session so the GUI can display.
#
# PATH resolution (first hit wins):
#   1. $ANONYMIZER_BIN
#   2. $HOME/.local/bin/anonymize
#   3. command -v anonymize

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run-anonymize.sh [options] [mode] file [file ...]
       run-anonymize.sh --templates-ui [--enabled id1,id2]

  --review              Document review window before saving
  --redact-style STYLE  placeholder | remove (default: placeholder)
  --format FMT          md | source | both (default: md)
  --config PATH         YAML config file
  --template IDS        Template packs for this run (comma-separated)
  --learn-to ID         Teach review decisions into user template
  --templates-ui        Open Templates… dialog (shared Tk UI)
  --enabled IDS         Starting selection for --templates-ui
  --allow-from PATH     Legacy allowlist file (one string per line)
  --deny-from PATH      Legacy denylist file (one string per line)
  --out-dir PATH        Write all outputs under PATH
  mode                  strict (default) | standard | extract
  file                  PDF, DOCX, or text path(s)

Stdout (success): one OUTPUT:/abs/path line per written file (MD and/or native).
--templates-ui stdout: ENABLED:id1,id2  or  CANCEL

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
  base=$(basename -- "$input_path")
  if [[ -n "${OUT_DIR:-}" ]]; then
    dir=$(cd "$OUT_DIR" && pwd)
  else
    dir=$(cd "$(dirname -- "$input_path")" && pwd)
  fi
  if [[ "$base" == *.* ]]; then
    stem="${base%.*}"
  else
    stem="$base"
  fi

  if [[ "$mode" == "extract" ]]; then
    name="${stem}.md"
    in_abs="$(cd "$(dirname -- "$input_path")" && pwd)/${base}"
    out_abs="${dir}/${name}"
    if [[ "$in_abs" == "$out_abs" ]]; then
      name="${stem}.extracted.md"
    fi
  else
    name="${stem}.anonymized.md"
  fi
  printf '%s/%s\n' "$dir" "$name"
}

# Native redacted path: {stem}.anonymized.pdf|.docx when input is PDF/DOCX.
expected_native_output_path() {
  local input_path="$1"
  local dir base stem ext name
  base=$(basename -- "$input_path")
  if [[ -n "${OUT_DIR:-}" ]]; then
    dir=$(cd "$OUT_DIR" && pwd)
  else
    dir=$(cd "$(dirname -- "$input_path")" && pwd)
  fi
  ext="${base##*.}"
  ext=$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')
  if [[ "$base" == *.* ]]; then
    stem="${base%.*}"
  else
    return 1
  fi
  case "$ext" in
    pdf) name="${stem}.anonymized.pdf" ;;
    docx) name="${stem}.anonymized.docx" ;;
    *) return 1 ;;
  esac
  printf '%s/%s\n' "$dir" "$name"
}

# Build a temp YAML config from optional --config, --allow-from, --deny-from, style.
# Prints path to temp file (caller should not delete until process ends).
build_merged_config() {
  local base_config="${1:-}"
  local allow_from="${2:-}"
  local deny_from="${3:-}"
  local style="${4:-}"
  local tmp
  tmp="$(mktemp "${TMPDIR:-/tmp}/anonymizer-gui-XXXXXX.yaml")"

  {
    if [[ -n "$base_config" && -f "$base_config" ]]; then
      # Start from user config (mode may still be overridden by CLI verb)
      cat "$base_config"
      echo
    fi
    if [[ -n "$style" ]]; then
      echo "redact_style: $(printf '%s' "$style" | sed 's/:/\\:/g')"
    fi
    if [[ -n "$allow_from" && -f "$allow_from" ]]; then
      echo "allowlist:"
      local any_allow=0
      while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -z "$line" || "$line" == \#* ]] && continue
        any_allow=1
        esc=$(printf '%s' "$line" | sed 's/\\/\\\\/g; s/"/\\"/g')
        printf '  - "%s"\n' "$esc"
      done <"$allow_from"
      # Explicit empty list replaces engine defaults
      if [[ "$any_allow" -eq 0 ]]; then
        echo "  []"
      fi
    fi
    if [[ -n "$deny_from" && -f "$deny_from" ]]; then
      echo "denylist:"
      local any_deny=0
      while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -z "$line" || "$line" == \#* ]] && continue
        any_deny=1
        esc=$(printf '%s' "$line" | sed 's/\\/\\\\/g; s/"/\\"/g')
        printf '  - text: "%s"\n' "$esc"
        printf '    entity_type: ORG\n'
      done <"$deny_from"
      if [[ "$any_deny" -eq 0 ]]; then
        echo "  []"
      fi
    fi
  } >"$tmp"
  printf '%s\n' "$tmp"
}

REVIEW=0
REDACT_STYLE=""
OUTPUT_FORMAT=""
CONFIG_PATH=""
ALLOW_FROM=""
DENY_FROM=""
TEMPLATE_IDS=""
LEARN_TO=""
OUT_DIR=""
TEMPLATES_UI=0
UI_ENABLED=""
UI_OUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --review)
      REVIEW=1
      shift
      ;;
    --redact-style)
      REDACT_STYLE="${2:-}"
      shift 2
      ;;
    --format)
      OUTPUT_FORMAT="${2:-}"
      shift 2
      ;;
    --config)
      CONFIG_PATH="${2:-}"
      shift 2
      ;;
    --template|--templates)
      TEMPLATE_IDS="${2:-}"
      shift 2
      ;;
    --learn-to)
      LEARN_TO="${2:-}"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="${2:-}"
      shift 2
      ;;
    --templates-ui)
      TEMPLATES_UI=1
      shift
      ;;
    --enabled)
      UI_ENABLED="${2:-}"
      shift 2
      ;;
    --out)
      UI_OUT="${2:-}"
      shift 2
      ;;
    --allow-from)
      ALLOW_FROM="${2:-}"
      shift 2
      ;;
    --deny-from)
      DENY_FROM="${2:-}"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

# Shared Templates dialog (Mac droplet Templates… button)
if [[ "$TEMPLATES_UI" -eq 1 ]]; then
  BIN="$(find_anonymize)" || exit 1
  UI_ARGS=(templates-ui)
  if [[ -n "$UI_ENABLED" ]]; then
    UI_ARGS+=(--enabled "$UI_ENABLED")
  fi
  if [[ -n "$UI_OUT" ]]; then
    UI_ARGS+=(--out "$UI_OUT")
  fi
  # Do not use set -e failure mask: preserve exit 2 = Cancel
  set +e
  "$BIN" "${UI_ARGS[@]}"
  ui_rc=$?
  set -e
  exit "$ui_rc"
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

# Document window needs a display, not a TTY; Terminal is still the usual host.

BIN="$(find_anonymize)" || exit 2

MERGED_CONFIG=""
EXTRA_ARGS=()
if [[ -n "$CONFIG_PATH" || -n "$ALLOW_FROM" || -n "$DENY_FROM" || -n "$REDACT_STYLE" ]]; then
  if [[ -n "$ALLOW_FROM" || -n "$DENY_FROM" || ( -n "$REDACT_STYLE" && -n "$CONFIG_PATH" ) ]]; then
    MERGED_CONFIG="$(build_merged_config "$CONFIG_PATH" "$ALLOW_FROM" "$DENY_FROM" "$REDACT_STYLE")"
    EXTRA_ARGS+=(--config "$MERGED_CONFIG")
  elif [[ -n "$CONFIG_PATH" ]]; then
    EXTRA_ARGS+=(--config "$CONFIG_PATH")
  fi
  if [[ -n "$REDACT_STYLE" ]]; then
    # CLI flag wins over YAML when both present
    EXTRA_ARGS+=(--redact-style "$REDACT_STYLE")
  fi
fi
if [[ -n "$OUTPUT_FORMAT" ]]; then
  EXTRA_ARGS+=(--format "$OUTPUT_FORMAT")
fi
if [[ -n "$TEMPLATE_IDS" ]]; then
  EXTRA_ARGS+=(--template "$TEMPLATE_IDS")
fi
if [[ -n "$LEARN_TO" ]]; then
  EXTRA_ARGS+=(--learn-to "$LEARN_TO")
fi
if [[ -n "$OUT_DIR" ]]; then
  mkdir -p "$OUT_DIR"
  EXTRA_ARGS+=(--out-dir "$OUT_DIR")
fi
cleanup_config() {
  if [[ -n "${MERGED_CONFIG:-}" && -f "$MERGED_CONFIG" ]]; then
    rm -f "$MERGED_CONFIG"
  fi
}
trap cleanup_config EXIT

ok=0
fail=0
outputs=()

for f in "$@"; do
  if [[ ! -e "$f" ]]; then
    echo "error: path not found: $f" >&2
    fail=$((fail + 1))
    continue
  fi
  if command -v realpath >/dev/null 2>&1; then
    f_abs=$(realpath "$f")
  else
    f_abs=$(cd "$(dirname -- "$f")" && pwd)/$(basename -- "$f")
  fi

  emit_outputs() {
    local f_abs="$1" mode="$2" fmt="${3:-md}"
    local out_path native_path
    # Markdown unless format is source-only
    if [[ "$fmt" != "source" && "$fmt" != "native" && "$fmt" != "original" ]]; then
      out_path=$(expected_output_path "$f_abs" "$mode")
      if [[ -f "$out_path" ]]; then
        printf 'OUTPUT:%s\n' "$out_path"
        outputs+=("$out_path")
      elif [[ "$fmt" == "md" || -z "$fmt" ]]; then
        echo "warning: expected output missing: $out_path" >&2
      fi
    fi
    # Native when format is source or both
    case "$fmt" in
      source|native|original|both|all|dual)
        if native_path=$(expected_native_output_path "$f_abs"); then
          if [[ -f "$native_path" ]]; then
            printf 'OUTPUT:%s\n' "$native_path"
            outputs+=("$native_path")
          else
            echo "warning: expected native output missing: $native_path" >&2
          fi
        fi
        ;;
    esac
  }

  FMT="${OUTPUT_FORMAT:-md}"
  if [[ "$REVIEW" -eq 1 ]]; then
    if "$BIN" "$MODE" "$f_abs" --review-window "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"; then
      emit_outputs "$f_abs" "$MODE" "$FMT"
      ok=$((ok + 1))
    else
      echo "error: anonymize failed for: $f_abs" >&2
      fail=$((fail + 1))
    fi
  else
    if "$BIN" "$MODE" "$f_abs" --quiet "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"; then
      emit_outputs "$f_abs" "$MODE" "$FMT"
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
