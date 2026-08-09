#!/usr/bin/env bash
# install.sh — Install anonymizer CLI on macOS (Linux experimental).
#
# Usage:
#   ./scripts/install.sh                  # from a cloned repo
#   ./scripts/install.sh --yes            # non-interactive
#   curl -fsSL .../install.sh | bash -s -- --yes
#
# Options:
#   --prefix DIR     Install root (default: ~/.local/share/anonymizer)
#   --bin-dir DIR    CLI symlink dir (default: ~/.local/bin)
#   --from-source    Use current/repo source instead of cloning
#   --repo URL       Git clone URL (default: https://github.com/arcane-tl/anonymizer.git)
#   --branch NAME    Git branch (default: main)
#   --no-ocr         Skip Homebrew OCR packages (tesseract/ocrmypdf)
#   --with-dev       Also install pytest etc.
#   --models sm|md|lg  spaCy model size (default: lg — best PERSON/ORG quality)
#   --python PATH      Python 3.11+ interpreter
#   -y, --yes          Assume yes / non-interactive
#   -h, --help         Show help

set -euo pipefail

PREFIX="${ANONYMIZER_PREFIX:-$HOME/.local/share/anonymizer}"
BIN_DIR="${ANONYMIZER_BIN_DIR:-$HOME/.local/bin}"
REPO_URL="${ANONYMIZER_REPO:-https://github.com/arcane-tl/anonymizer.git}"
BRANCH="${ANONYMIZER_BRANCH:-main}"
FROM_SOURCE=0
WITH_OCR=1
WITH_DEV=0
MODELS="lg"
PYTHON_BIN=""
ASSUME_YES=0

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
CYAN=$'\033[0;36m'
BOLD=$'\033[1m'
RESET=$'\033[0m'

info()  { printf '%s==>%s %s\n' "$CYAN" "$RESET" "$*"; }
ok()    { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
warn()  { printf '%s!%s %s\n' "$YELLOW" "$RESET" "$*"; }
err()   { printf '%serror:%s %s\n' "$RED" "$RESET" "$*" >&2; }
die()   { err "$*"; exit 1; }

usage() {
  cat <<'EOF'
install.sh — Install anonymizer CLI on macOS (Linux experimental).

Usage:
  ./scripts/install.sh                  # from a cloned repo
  ./scripts/install.sh --yes            # non-interactive
  curl -fsSL .../install.sh | bash -s -- --yes

Options:
  --prefix DIR     Install root (default: ~/.local/share/anonymizer)
  --bin-dir DIR    CLI symlink dir (default: ~/.local/bin)
  --from-source    Use current/repo source instead of cloning
  --repo URL       Git clone URL (default: GitHub arcane-tl/anonymizer)
  --branch NAME    Git branch (default: main)
  --no-ocr         Skip Homebrew OCR packages (tesseract/ocrmypdf)
  --with-dev         Also install pytest etc.
  --models sm|md|lg  spaCy size (default: lg — best NER quality; sm = smaller/faster)
  --python PATH      Python 3.11+ interpreter
  -y, --yes          Assume yes / non-interactive
  -h, --help         Show help

Default models: English + Finnish large (en_core_web_lg, fi_core_news_lg).
Swedish and other languages are optional after install — see docs/models.md.
EOF
}

confirm() {
  local prompt=$1
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    return 0
  fi
  if [[ ! -t 0 ]]; then
    # stdin is a pipe (curl | bash) — require --yes
    die "Non-interactive install requires --yes (e.g. bash -s -- --yes)"
  fi
  read -r -p "$prompt [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" || "$ans" == "yes" ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --from-source) FROM_SOURCE=1; shift ;;
    --repo) REPO_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --no-ocr) WITH_OCR=0; shift ;;
    --with-dev) WITH_DEV=1; shift ;;
    --models) MODELS="$2"; shift 2 ;;
    --python) PYTHON_BIN="$2"; shift 2 ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1 (try --help)" ;;
  esac
done

if [[ "$MODELS" != "sm" && "$MODELS" != "md" && "$MODELS" != "lg" ]]; then
  die "--models must be sm, md, or lg (default: lg)"
fi

# ---------------------------------------------------------------------------
# Locate source tree
# ---------------------------------------------------------------------------
SCRIPT_PATH="${BASH_SOURCE[0]:-}"
SOURCE_DIR=""

if [[ -n "$SCRIPT_PATH" && -f "$SCRIPT_PATH" ]]; then
  # Resolve when script path is real (not curl | bash with no file)
  _script_dir="$(cd "$(dirname "$SCRIPT_PATH")" 2>/dev/null && pwd || true)"
  if [[ -n "$_script_dir" && -f "$_script_dir/../pyproject.toml" ]]; then
    SOURCE_DIR="$(cd "$_script_dir/.." && pwd)"
  fi
fi

# Also detect cwd as source
if [[ -z "$SOURCE_DIR" && -f "./pyproject.toml" ]] && grep -q 'name = "anonymizer"' ./pyproject.toml 2>/dev/null; then
  SOURCE_DIR="$(pwd)"
fi

# curl | bash often has BASH_SOURCE as empty or stdin — force clone unless --from-source with SOURCE_DIR
if [[ "$FROM_SOURCE" -eq 1 ]]; then
  [[ -n "$SOURCE_DIR" ]] || die "--from-source requires running from a cloned anonymizer repo"
fi

OS="$(uname -s)"
info "anonymizer installer"
info "OS: $OS"

# ---------------------------------------------------------------------------
# Find Python 3.11+
# ---------------------------------------------------------------------------
find_python() {
  local candidates=()
  if [[ -n "$PYTHON_BIN" ]]; then
    candidates=("$PYTHON_BIN")
  else
    candidates=(
      python3.13 python3.12 python3.11
      python3
      /opt/homebrew/bin/python3
      /usr/local/bin/python3
    )
  fi
  local c ver major minor
  for c in "${candidates[@]}"; do
    if command -v "$c" >/dev/null 2>&1 || [[ -x "$c" ]]; then
      ver="$("$c" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
      major="${ver%%.*}"
      minor="${ver#*.}"
      if [[ -n "$major" && "$major" -gt 3 ]] || { [[ "$major" -eq 3 && "$minor" -ge 11 ]]; }; then
        echo "$c"
        return 0
      fi
    fi
  done
  return 1
}

PY="$(find_python || true)"
if [[ -z "$PY" ]]; then
  if [[ "$OS" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
    warn "No Python 3.11+ found. Installing python@3.12 via Homebrew…"
    brew install python@3.12
    PY="$(find_python || true)"
  fi
fi
[[ -n "$PY" ]] || die "Python 3.11+ is required. Install it (e.g. brew install python@3.12) and re-run."
ok "Python: $PY ($("$PY" -c 'import sys; print(sys.version.split()[0])'))"

# ---------------------------------------------------------------------------
# Optional OCR system packages (macOS Homebrew)
# ---------------------------------------------------------------------------
install_ocr() {
  if [[ "$WITH_OCR" -eq 0 ]]; then
    warn "Skipping OCR system packages (--no-ocr)"
    return 0
  fi
  if [[ "$OS" != "Darwin" ]]; then
    warn "OCR auto-install is macOS/Homebrew only. Install tesseract + eng/fin packs yourself for scanned PDFs."
    return 0
  fi
  if ! command -v brew >/dev/null 2>&1; then
    warn "Homebrew not found — skipping OCR packages. Install from https://brew.sh then: brew install tesseract tesseract-lang ocrmypdf"
    return 0
  fi
  info "Installing OCR packages (tesseract, tesseract-lang, ocrmypdf)…"
  brew list tesseract >/dev/null 2>&1 || brew install tesseract
  brew list tesseract-lang >/dev/null 2>&1 || brew install tesseract-lang
  brew list ocrmypdf >/dev/null 2>&1 || brew install ocrmypdf
  if command -v tesseract >/dev/null 2>&1; then
    if tesseract --list-langs 2>/dev/null | grep -q '^fin$'; then
      ok "Tesseract with eng + fin"
    else
      warn "Tesseract installed but 'fin' language pack not listed. Try: brew reinstall tesseract-lang"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Obtain project files
# ---------------------------------------------------------------------------
ensure_source() {
  if [[ -n "$SOURCE_DIR" && ( "$FROM_SOURCE" -eq 1 || -f "$SOURCE_DIR/pyproject.toml" ) ]]; then
    # Install into PREFIX but use local source (editable) when --from-source
    if [[ "$FROM_SOURCE" -eq 1 ]]; then
      INSTALL_ROOT="$SOURCE_DIR"
      EDITABLE=1
      ok "Using source tree: $INSTALL_ROOT"
      return 0
    fi
  fi

  # Clone or update into PREFIX
  INSTALL_ROOT="$PREFIX"
  EDITABLE=1
  mkdir -p "$(dirname "$PREFIX")"
  if [[ -d "$PREFIX/.git" ]]; then
    info "Updating existing install at $PREFIX …"
    git -C "$PREFIX" fetch --quiet origin "$BRANCH" || true
    git -C "$PREFIX" checkout --quiet "$BRANCH" || true
    git -C "$PREFIX" pull --ff-only --quiet origin "$BRANCH" || warn "git pull failed; using existing tree"
  elif [[ -d "$PREFIX" && -f "$PREFIX/pyproject.toml" ]]; then
    ok "Using existing tree at $PREFIX"
  else
    if [[ -n "$SOURCE_DIR" && -f "$SOURCE_DIR/pyproject.toml" ]]; then
      info "Copying source from $SOURCE_DIR → $PREFIX"
      mkdir -p "$PREFIX"
      # Prefer rsync if available; else tar
      if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete \
          --exclude '.venv' --exclude '.git' --exclude '__pycache__' \
          --exclude '.pytest_cache' --exclude 'samples/out' \
          --exclude '*.egg-info' --exclude 'dist' --exclude 'build' \
          "$SOURCE_DIR/" "$PREFIX/"
        # Keep a note of origin if git exists in source
        if [[ -d "$SOURCE_DIR/.git" ]]; then
          git -C "$SOURCE_DIR" remote get-url origin >/dev/null 2>&1 && \
            echo "source_repo=$(git -C "$SOURCE_DIR" remote get-url origin)" >"$PREFIX/.install-meta" || true
        fi
      else
        mkdir -p "$PREFIX"
        tar -C "$SOURCE_DIR" \
          --exclude='.venv' --exclude='.git' --exclude='__pycache__' \
          --exclude='.pytest_cache' --exclude='samples/out' \
          -cf - . | tar -C "$PREFIX" -xf -
      fi
    else
      info "Cloning $REPO_URL (branch $BRANCH) → $PREFIX"
      if [[ -d "$PREFIX" ]]; then
        # non-empty non-git dir
        if [[ -n "$(ls -A "$PREFIX" 2>/dev/null || true)" ]]; then
          die "Prefix $PREFIX exists and is not a git checkout. Remove it or pick another --prefix."
        fi
      fi
      git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$PREFIX"
    fi
  fi
  ok "Install root: $INSTALL_ROOT"
}

# ---------------------------------------------------------------------------
# venv + pip + models + PATH wrapper
# ---------------------------------------------------------------------------
setup_python_env() {
  local venv="$INSTALL_ROOT/.venv"
  info "Creating virtualenv at $venv"
  "$PY" -m venv "$venv"
  # shellcheck disable=SC1091
  source "$venv/bin/activate"
  python -m pip install --upgrade pip setuptools wheel >/dev/null

  info "Installing anonymizer package…"
  if [[ "$WITH_DEV" -eq 1 ]]; then
    pip install -e "${INSTALL_ROOT}[dev]"
  else
    pip install -e "${INSTALL_ROOT}"
  fi

  info "Installing spaCy models (en+fi, size=$MODELS; may take several minutes)…"
  if python -m anonymizer.install_models --langs en,fi --size "$MODELS" --fallback; then
    ok "spaCy EN+FI models ready"
  else
    warn "spaCy model install incomplete — CLI is installed; retry:"
    warn "  $venv/bin/python -m anonymizer.install_models --langs en,fi --size $MODELS --fallback"
    warn "  See docs/models.md"
  fi
  ok "Python package installed"
}

install_launcher() {
  mkdir -p "$BIN_DIR"
  local launcher="$BIN_DIR/anonymize"
  local venv_anonymize="$INSTALL_ROOT/.venv/bin/anonymize"

  [[ -x "$venv_anonymize" ]] || die "Expected CLI at $venv_anonymize not found"

  # Wrapper so upgrades to venv keep working via same path
  cat >"$launcher" <<EOF
#!/usr/bin/env bash
# Generated by anonymizer install.sh — do not edit.
exec "$INSTALL_ROOT/.venv/bin/anonymize" "\$@"
EOF
  chmod +x "$launcher"
  ok "CLI installed: $launcher"

  # Optional: symlink into Homebrew-style bins when writable (often already on PATH)
  local brew_bin
  for brew_bin in /opt/homebrew/bin /usr/local/bin; do
    if [[ -d "$brew_bin" && -w "$brew_bin" ]]; then
      ln -sf "$launcher" "$brew_bin/anonymize" 2>/dev/null && \
        ok "Also linked: $brew_bin/anonymize" && break
    fi
  done

  local export_line="export PATH=\"$BIN_DIR:\$PATH\""
  if echo ":$PATH:" | grep -q ":$BIN_DIR:"; then
    ok "$BIN_DIR is on PATH"
    return 0
  fi
  # Homebrew bin may already provide the command
  if command -v anonymize >/dev/null 2>&1; then
    ok "anonymize is available on PATH ($(command -v anonymize))"
    return 0
  fi

  warn "$BIN_DIR is not on your PATH"
  # Only auto-edit shell rc for the default user bin dir, and never for
  # custom --bin-dir (avoids polluting config during tests / alternate installs).
  local default_bin="$HOME/.local/bin"
  if [[ "$BIN_DIR" != "$default_bin" ]]; then
    warn "Add manually: $export_line"
    return 0
  fi

  local shell_rc=""
  if [[ -n "${SHELL:-}" ]]; then
    case "$SHELL" in
      */zsh) shell_rc="$HOME/.zshrc" ;;
      */bash)
        if [[ -f "$HOME/.bash_profile" ]]; then
          shell_rc="$HOME/.bash_profile"
        else
          shell_rc="$HOME/.bashrc"
        fi
        ;;
      *) shell_rc="" ;;
    esac
  fi

  if [[ -z "$shell_rc" ]]; then
    warn "Add manually: $export_line"
    return 0
  fi

  if grep -qF "$BIN_DIR" "$shell_rc" 2>/dev/null; then
    ok "$BIN_DIR already referenced in $shell_rc"
    return 0
  fi

  # --yes: still update default PATH (expected for one-liner installs)
  if [[ "$ASSUME_YES" -eq 1 ]] || confirm "Add $BIN_DIR to PATH in $shell_rc?"; then
    {
      echo ""
      echo "# anonymizer CLI"
      echo "$export_line"
    } >>"$shell_rc"
    ok "Added PATH line to $shell_rc (restart shell or: source $shell_rc)"
  else
    warn "Add manually: $export_line"
  fi
}

verify_install() {
  info "Verifying install…"
  local cli="$BIN_DIR/anonymize"
  "$cli" --version
  if "$cli" doctor >/dev/null 2>&1; then
    ok "anonymize doctor passed"
  else
    # Still print doctor output for the user
    "$cli" doctor || warn "doctor reported issues — see above"
  fi
  ok "anonymize is ready"
}

print_summary() {
  local path_hint=""
  if ! command -v anonymize >/dev/null 2>&1; then
    path_hint=$(
      cat <<EOF

${YELLOW}PATH tip (this terminal only):${RESET}
  export PATH="$BIN_DIR:\$PATH"

  Or open a ${BOLD}new terminal window${RESET} (installer may have updated your shell rc).
EOF
    )
  fi

  cat <<EOF

${BOLD}${GREEN}Installation complete${RESET}

  Install root:  $INSTALL_ROOT
  CLI:           $BIN_DIR/anonymize
  Config sample: $INSTALL_ROOT/config.example.yaml
$path_hint
${BOLD}Try it:${RESET}
  anonymize doctor
  anonymize extract path/to/document.pdf
  anonymize path/to/document.pdf
  anonymize standard path/to/contract.pdf

  anonymize examples          # more copy-paste commands
  anonymize --help

${BOLD}spaCy models (default: EN+FI large):${RESET}
  Retry / resize:     $INSTALL_ROOT/.venv/bin/python -m anonymizer.install_models --langs en,fi --size lg
  Smaller:            … --size sm
  Optional Swedish:   $INSTALL_ROOT/.venv/bin/python -m anonymizer.install_models --langs sv --size lg
                      anonymize doc.pdf --lang sv
  Full guide:         docs/models.md

${BOLD}Upgrade later:${RESET}
  $INSTALL_ROOT/scripts/install.sh --yes --from-source
  # or re-run the curl installer to pull latest main

${BOLD}Uninstall:${RESET}
  $INSTALL_ROOT/scripts/uninstall.sh

EOF
}

# ---------------------------------------------------------------------------
main() {
  install_ocr
  ensure_source
  setup_python_env
  install_launcher
  verify_install
  print_summary
}

main
