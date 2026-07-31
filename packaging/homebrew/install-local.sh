#!/usr/bin/env bash
# install-local.sh — Copy formula into a local Homebrew tap and install.
#
# Usage (from repo root or this directory):
#   ./packaging/homebrew/install-local.sh           # stable-style from local tarball of HEAD
#   ./packaging/homebrew/install-local.sh --head    # brew --HEAD from GitHub main
#
# Requires: brew, network (for pip deps + spaCy models)

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
HEAD=0
if [[ "${1:-}" == "--head" ]]; then
  HEAD=1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "error: Homebrew not found (https://brew.sh)" >&2
  exit 2
fi

export HOMEBREW_NO_REQUIRE_TAP_TRUST="${HOMEBREW_NO_REQUIRE_TAP_TRUST:-1}"

TAP_NAME="arcane-tl/anonymizer"
# Ensure tap directory exists
if ! brew --repository "$TAP_NAME" >/dev/null 2>&1; then
  brew tap-new --no-git "$TAP_NAME" 2>/dev/null || true
fi
TAP="$(brew --repository "$TAP_NAME")"
mkdir -p "$TAP/Formula"

if [[ "$HEAD" -eq 1 ]]; then
  cp "$HERE/anonymizer.rb" "$TAP/Formula/anonymizer.rb"
  echo "==> Installing arcane-tl/anonymizer/anonymizer (--HEAD from GitHub)"
  brew uninstall --ignore-dependencies anonymizer 2>/dev/null || true
  brew install --HEAD --build-from-source "$TAP_NAME/anonymizer"
else
  # Package current git tree as a local 1.0.0 tarball (works before GitHub tag)
  TMP_TGZ="$(mktemp -t anonymizer-XXXXXX).tar.gz"
  cleanup() { rm -f "$TMP_TGZ"; }
  trap cleanup EXIT
  (
    cd "$REPO"
    git archive --format=tar.gz --prefix=anonymizer-1.0.0/ -o "$TMP_TGZ" HEAD
  )
  SHA="$(shasum -a 256 "$TMP_TGZ" | awk '{print $1}')"
  # file:// URL for local smoke / offline-from-clone install
  sed -e "s|REPLACE_AFTER_TAGGING_V1_0_0|${SHA}|" \
      -e "s|https://github.com/arcane-tl/anonymizer/archive/refs/tags/v1.0.0.tar.gz|file://${TMP_TGZ}|" \
      "$HERE/anonymizer.rb" >"$TAP/Formula/anonymizer.rb"
  echo "==> Installing arcane-tl/anonymizer/anonymizer from local tree (1.0.0)"
  brew uninstall --ignore-dependencies anonymizer 2>/dev/null || true
  # Drop conflicting non-brew symlink if present
  if [[ -L "$(brew --prefix)/bin/anonymize" ]] && [[ ! -e "$(brew --prefix)/opt/anonymizer/bin/anonymize" ]]; then
    rm -f "$(brew --prefix)/bin/anonymize" || true
  fi
  brew install --build-from-source "$TAP_NAME/anonymizer" || true
  # Link even if linkage fixup warned
  brew link --overwrite anonymizer 2>/dev/null || true
fi

echo
echo "Try:"
echo "  $(brew --prefix)/opt/anonymizer/bin/anonymize --version"
echo "  anonymize doctor   # if brew bin is first on PATH"
