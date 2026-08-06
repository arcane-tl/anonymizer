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

# Custom app icon (document + magnifier/lock)
# Modern macOS prefers CFBundleIconName + Assets.car (default droplet art).
# Force our .icns to win by replacing every default icon resource.
ICNS="$HERE/icons/Anonymizer.icns"
PNG="$HERE/icons/Anonymizer-transparent.png"
if [[ ! -f "$PNG" ]]; then
  PNG="$HERE/icons/Anonymizer-1024.png"
fi
if [[ -f "$ICNS" ]]; then
  echo "==> Applying custom icon…"
  cp "$ICNS" "$RES/Anonymizer.icns"
  cp "$ICNS" "$RES/droplet.icns"
  cp "$ICNS" "$RES/applet.icns" 2>/dev/null || true
  # Asset catalog overrides CFBundleIconFile on recent macOS — remove it
  rm -f "$RES/Assets.car"
  # Legacy resource-fork icon from osacompile
  rm -f "$RES/droplet.rsrc" "$RES/applet.rsrc"

  PLIST="$STAGE/Contents/Info.plist"
  if [[ -f "$PLIST" ]]; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile Anonymizer" "$PLIST" 2>/dev/null \
      || /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string Anonymizer" "$PLIST" 2>/dev/null \
      || true
    # Point named icon at our file, not "droplet"
    /usr/libexec/PlistBuddy -c "Set :CFBundleIconName Anonymizer" "$PLIST" 2>/dev/null \
      || /usr/libexec/PlistBuddy -c "Add :CFBundleIconName string Anonymizer" "$PLIST" 2>/dev/null \
      || true
  fi
fi

TARGET="$DEST_DIR/$NAME"
if [[ -e "$TARGET" ]]; then
  echo "==> Replacing existing $TARGET"
  rm -rf "$TARGET"
fi
mv "$STAGE" "$TARGET"

# Set Finder custom icon (most reliable for osacompile droplets).
# Bundle .icns alone is often ignored in favor of Assets.car / droplet defaults;
# `fileicon` writes Icon\r + FinderInfo so Get Info / Dock show our art.
if [[ -f "$PNG" ]] || [[ -f "$ICNS" ]]; then
  ICON_SRC="$PNG"
  [[ -f "$ICON_SRC" ]] || ICON_SRC="$ICNS"
  echo "==> Registering custom Finder icon…"
  if command -v fileicon >/dev/null 2>&1; then
    fileicon set "$TARGET" "$ICON_SRC" || true
  else
    echo "    (optional) brew install fileicon  — improves Dock/Finder icon reliability"
  fi
fi

# Clear quarantine if present (user-downloaded repo)
if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null || true
fi

# Bust icon services cache for this app
touch "$TARGET"
touch "$TARGET/Contents/Info.plist"
if command -v /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister >/dev/null 2>&1; then
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
    -f "$TARGET" 2>/dev/null || true
fi
# User-level icon cache (Finder may need a relaunch to refresh)
rm -rf "${HOME}/Library/Caches/com.apple.iconservices.store" 2>/dev/null || true
find "${HOME}/Library/Caches/com.apple.iconservices.store" -delete 2>/dev/null || true

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
