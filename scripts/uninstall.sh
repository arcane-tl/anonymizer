#!/usr/bin/env bash
# uninstall.sh — Remove anonymizer CLI install created by install.sh
#
# Usage:
#   ./scripts/uninstall.sh
#   ./scripts/uninstall.sh --prefix ~/.local/share/anonymizer --yes

set -euo pipefail

PREFIX="${ANONYMIZER_PREFIX:-$HOME/.local/share/anonymizer}"
BIN_DIR="${ANONYMIZER_BIN_DIR:-$HOME/.local/bin}"
ASSUME_YES=0
REMOVE_PREFIX=1

info() { printf '==> %s\n' "$*"; }
ok()   { printf '✓ %s\n' "$*"; }
warn() { printf '! %s\n' "$*"; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --keep-files) REMOVE_PREFIX=0; shift ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    -h|--help)
      sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
done

confirm() {
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    return 0
  fi
  read -r -p "$1 [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" || "$ans" == "yes" ]]
}

LAUNCHER="$BIN_DIR/anonymize"

# Only remove launcher if it points at this PREFIX
if [[ -e "$LAUNCHER" || -L "$LAUNCHER" ]]; then
  if grep -q "$PREFIX" "$LAUNCHER" 2>/dev/null || \
     [[ "$(readlink "$LAUNCHER" 2>/dev/null || true)" == *"$PREFIX"* ]]; then
    if confirm "Remove CLI launcher $LAUNCHER?"; then
      rm -f "$LAUNCHER"
      ok "Removed $LAUNCHER"
    fi
  else
    warn "Launcher $LAUNCHER does not reference $PREFIX — leaving it alone"
  fi
else
  info "No launcher at $LAUNCHER"
fi

# Detect if we are uninstalling an in-repo --from-source install (only remove venv + launcher)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "$PREFIX" == "$REPO_ROOT" ]] || [[ "$(pwd)" == "$REPO_ROOT" && "$REMOVE_PREFIX" -eq 1 ]]; then
  # If prefix is the git repo itself, only drop .venv
  if [[ -d "$REPO_ROOT/.venv" ]]; then
    if confirm "Remove virtualenv $REPO_ROOT/.venv?"; then
      rm -rf "$REPO_ROOT/.venv"
      ok "Removed $REPO_ROOT/.venv"
    fi
  fi
elif [[ -d "$PREFIX" && "$REMOVE_PREFIX" -eq 1 ]]; then
  if confirm "Remove install directory $PREFIX?"; then
    rm -rf "$PREFIX"
    ok "Removed $PREFIX"
  fi
fi

ok "Uninstall finished"
echo "Note: Homebrew packages (tesseract, ocrmypdf) were left installed."
echo "Remove them with: brew uninstall tesseract tesseract-lang ocrmypdf"
