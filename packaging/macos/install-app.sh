#!/usr/bin/env bash
# install-app.sh — Build Anonymizer.app (droplet) and install to ~/Applications.
#
# Usage:
#   ./packaging/macos/install-app.sh
#   ./packaging/macos/install-app.sh --dest /Applications
#
# Requires: macOS with osacompile (Xcode CLT not required for osacompile).
# The app calls the anonymize CLI (install that first via scripts/install.sh).

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST_DIR="${HOME}/Applications"
NAME="Anonymizer.app"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest) DEST_DIR="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,20p' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: Mac GUI install is only supported on macOS" >&2
  exit 2
fi

if ! command -v osacompile >/dev/null 2>&1; then
  echo "error: osacompile not found (macOS AppleScript compiler)" >&2
  exit 2
fi

if [[ ! -f "$HERE/Anonymizer.applescript" || ! -f "$HERE/run-anonymize.sh" ]]; then
  echo "error: missing Anonymizer.applescript or run-anonymize.sh in $HERE" >&2
  exit 2
fi

mkdir -p "$DEST_DIR"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/anonymizer-app.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

STAGE="$TMP/$NAME"
echo "==> Compiling droplet…"
osacompile -o "$STAGE" "$HERE/Anonymizer.applescript"

RES="$STAGE/Contents/Resources"
mkdir -p "$RES"
cp "$HERE/run-anonymize.sh" "$RES/run-anonymize.sh"
chmod +x "$RES/run-anonymize.sh"

# Optional: keep a copy of the helper next to the script for debugging
# Bundle identifier-ish via Info.plist tweak is optional for MVP

TARGET="$DEST_DIR/$NAME"
if [[ -e "$TARGET" ]]; then
  echo "==> Replacing existing $TARGET"
  rm -rf "$TARGET"
fi
mv "$STAGE" "$TARGET"

# Clear quarantine if present (user-downloaded repo)
if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null || true
fi

echo "✓ Installed: $TARGET"
echo
echo "Next steps:"
echo "  1. Ensure CLI works:  anonymize doctor"
echo "  2. Open Finder → Applications (or ~/Applications)"
echo "  3. Drag a PDF/DOCX/txt onto Anonymizer"
echo "  4. Pick mode → Markdown appears next to the source file"
echo
if ! command -v anonymize >/dev/null 2>&1 && [[ ! -x "${HOME}/.local/bin/anonymize" ]]; then
  echo "Note: anonymize CLI not found on PATH yet."
  echo "  Install: curl -fsSL https://raw.githubusercontent.com/arcane-tl/anonymizer/main/scripts/install.sh | bash -s -- --yes"
fi
