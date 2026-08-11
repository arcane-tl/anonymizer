#!/usr/bin/env bash
# install-app.sh — Build Anonymizer.app (droplet) and install to ~/Applications.
#
# Usage:
#   ./packaging/macos/install-app.sh
#   ./packaging/macos/install-app.sh --dest /Applications
#   ./packaging/macos/install-app.sh --dest /tmp/stage --no-sign   # for release-app.sh
#
# Production releases (Developer ID + notarization): use release-app.sh instead.
#
# Requires: macOS with osacompile (Xcode CLT not required for osacompile).
# The app calls the anonymize CLI (install that first via scripts/install.sh or brew).

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST_DIR="${HOME}/Applications"
NAME="Anonymizer.app"
DO_SIGN=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest) DEST_DIR="$2"; shift 2 ;;
    --no-sign) DO_SIGN=0; shift ;;
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
if [[ -f "$HERE/lists-io.sh" ]]; then
  cp "$HERE/lists-io.sh" "$RES/lists-io.sh"
  chmod +x "$RES/lists-io.sh"
fi
if [[ -f "$HERE/templates-io.sh" ]]; then
  cp "$HERE/templates-io.sh" "$RES/templates-io.sh"
  chmod +x "$RES/templates-io.sh"
fi

# Canonical version from pyproject.toml (or ANONYMIZER_VERSION override)
ROOT="$(cd "$HERE/../.." && pwd)"
if [[ -x "$ROOT/scripts/version.sh" ]]; then
  APP_VERSION="$("$ROOT/scripts/version.sh")"
else
  APP_VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('$ROOT/pyproject.toml','rb'))['project']['version'])" 2>/dev/null || echo dev)"
fi
printf '%s' "$APP_VERSION" > "$RES/VERSION"
echo "==> Bundle version: $APP_VERSION"

# Squircle PNG for dialog title row (README asset). Dock/Finder still use .icns below.
DIALOG_PNG="$HERE/icons/Anonymizer-readme.png"
if [[ -f "$DIALOG_PNG" ]]; then
  cp "$DIALOG_PNG" "$RES/Anonymizer-dialog.png"
fi

# Custom app icon (document + magnifier/lock), full-bleed square .icns.
# Do NOT use `fileicon set` — Finder custom icons skip the system squircle
# and look sharp-cornered / wrong size next to real app icons.
ICNS="$HERE/icons/Anonymizer.icns"
if [[ -f "$ICNS" ]]; then
  echo "==> Applying bundle icon (system will apply rounded corners)…"
  cp "$ICNS" "$RES/Anonymizer.icns"
  cp "$ICNS" "$RES/droplet.icns"
  cp "$ICNS" "$RES/applet.icns" 2>/dev/null || true
  # Asset catalog / legacy rsrc override CFBundleIconFile on recent macOS
  rm -f "$RES/Assets.car" "$RES/droplet.rsrc" "$RES/applet.rsrc"

  PLIST="$STAGE/Contents/Info.plist"
  if [[ -f "$PLIST" ]]; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile Anonymizer" "$PLIST" 2>/dev/null \
      || /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string Anonymizer" "$PLIST" 2>/dev/null \
      || true
    # Named asset-catalog icons (CFBundleIconName) force "droplet" defaults —
    # delete so only CFBundleIconFile (.icns) is used.
    /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$PLIST" 2>/dev/null || true
  fi
fi

TARGET="$DEST_DIR/$NAME"
if [[ -e "$TARGET" ]]; then
  echo "==> Replacing existing $TARGET"
  # Drop any previous Finder custom icon (Icon\r) so the bundle icon is used
  if command -v fileicon >/dev/null 2>&1; then
    fileicon rm "$TARGET" 2>/dev/null || true
  fi
  rm -f "$TARGET/Icon"$'\r' 2>/dev/null || true
  rm -rf "$TARGET"
fi
mv "$STAGE" "$TARGET"

# Ensure no Finder custom-icon override on the new bundle
if command -v fileicon >/dev/null 2>&1; then
  fileicon rm "$TARGET" 2>/dev/null || true
fi
rm -f "$TARGET/Icon"$'\r' 2>/dev/null || true
# Clear custom-icon bit in FinderInfo if xattr tools available
if command -v xattr >/dev/null 2>&1; then
  xattr -d com.apple.FinderInfo "$TARGET" 2>/dev/null || true
  xattr -cr "$TARGET" 2>/dev/null || true
fi

# IMPORTANT: osacompile signs the bundle; editing Info.plist/.icns above invalidates
# that signature ("damaged" under Gatekeeper). Re-seal after all mutations.
# Production: release-app.sh re-signs with Developer ID + notarizes (use --no-sign).
# Dev default: ad-hoc sign so local installs are at least self-consistent.
if [[ "$DO_SIGN" -eq 1 ]]; then
  if command -v codesign >/dev/null 2>&1; then
    echo "==> Ad-hoc codesign (dev). For distribution use: packaging/macos/release-app.sh"
    codesign --force --deep --sign - "$TARGET"
    codesign --verify --deep --strict "$TARGET" 2>/dev/null \
      || echo "warning: codesign --verify reported issues (dev install may still work)" >&2
  fi
else
  echo "==> Skipping codesign (--no-sign); release-app.sh will seal with Developer ID"
fi

# Re-register with Launch Services and bust icon caches
touch "$TARGET" "$TARGET/Contents/Info.plist"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [[ -x "$LSREGISTER" ]]; then
  "$LSREGISTER" -f "$TARGET" 2>/dev/null || true
fi
rm -rf "${HOME}/Library/Caches/com.apple.iconservices.store" 2>/dev/null || true

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
