#!/usr/bin/env bash
# release-app.sh — Build, Developer ID–sign, notarize, staple, and zip Anonymizer.app
#
# One-time setup (this Mac):
#   1. Install "Developer ID Application" certificate in Keychain
#      security find-identity -v -p codesigning
#   2. Store notary credentials (App Store Connect API key .p8):
#      xcrun notarytool store-credentials anonymizer-notary \
#        --key ~/path/to/AuthKey_XXXXXXXXXX.p8 \
#        --key-id XXXXXXXXXX \
#        --issuer XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
#
# Usage:
#   ./packaging/macos/release-app.sh --version 1.0.1
#   ANONYMIZER_CODESIGN_IDENTITY="Developer ID Application: …" \
#     ./packaging/macos/release-app.sh --version 1.0.1
#
# Env overrides:
#   ANONYMIZER_CODESIGN_IDENTITY  — codesign -s identity (auto-detect Developer ID if unset)
#   ANONYMIZER_NOTARY_PROFILE     — notarytool keychain profile (default: anonymizer-notary)
#   ANONYMIZER_API_KEY_PATH       — path to AuthKey_*.p8 (skips keychain profile)
#   ANONYMIZER_API_KEY_ID         — Key ID (with API_KEY_PATH)
#   ANONYMIZER_API_ISSUER         — Issuer UUID (with API_KEY_PATH)
#   ANONYMIZER_SKIP_NOTARY        — set to 1 to only sign (no upload)
#
# Output: dist/Anonymizer-VERSION.zip + sha256 on stdout

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
NAME="Anonymizer.app"
VERSION=""
NOTARY_PROFILE="${ANONYMIZER_NOTARY_PROFILE:-anonymizer-notary}"
SKIP_NOTARY="${ANONYMIZER_SKIP_NOTARY:-0}"
OUT_DIR="${ROOT}/dist"

usage() {
  sed -n '1,35p' "$0"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --skip-notary) SKIP_NOTARY=1; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: release-app.sh only runs on macOS" >&2
  exit 2
fi

if [[ -z "$VERSION" ]]; then
  # Canonical: pyproject.toml via scripts/version.sh (ANONYMIZER_VERSION overrides)
  if [[ -x "$ROOT/scripts/version.sh" ]]; then
    VERSION="$("$ROOT/scripts/version.sh")"
  elif [[ -f "$ROOT/pyproject.toml" ]]; then
    VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('$ROOT/pyproject.toml','rb'))['project']['version'])" 2>/dev/null || true)"
  fi
fi
if [[ -z "$VERSION" ]]; then
  echo "error: pass --version X.Y.Z or set version in pyproject.toml" >&2
  exit 2
fi

pick_identity() {
  if [[ -n "${ANONYMIZER_CODESIGN_IDENTITY:-}" ]]; then
    printf '%s\n' "$ANONYMIZER_CODESIGN_IDENTITY"
    return 0
  fi
  # Prefer Developer ID Application (distribution / Gatekeeper)
  local line id
  line="$(security find-identity -v -p codesigning 2>/dev/null | grep -F 'Developer ID Application' | head -1 || true)"
  if [[ -n "$line" ]]; then
    # "  1) ABC123 \"Developer ID Application: Name (TEAM)\""
    id="${line#*\"}"
    id="${id%\"*}"
    printf '%s\n' "$id"
    return 0
  fi
  return 1
}

if ! IDENTITY="$(pick_identity)"; then
  cat >&2 <<'EOF'
error: no Developer ID Application codesigning identity found.

Install a certificate, then re-run:

  1. https://developer.apple.com/account/resources/certificates/list
     → + → Developer ID Application
  2. Keychain Access → Certificate Assistant → Request a Certificate From a
     Certificate Authority… → save CSR → upload → download .cer → open it
  3. Verify:
       security find-identity -v -p codesigning
     You should see: Developer ID Application: Your Name (TEAMID)

  Or set:
       export ANONYMIZER_CODESIGN_IDENTITY="Developer ID Application: … (TEAMID)"

EOF
  exit 2
fi

echo "==> Codesign identity: $IDENTITY"
echo "==> Version: $VERSION"

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/anonymizer-release.XXXXXX")"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

echo "==> Building unsigned bundle…"
"$HERE/install-app.sh" --dest "$STAGE" --no-sign
APP="$STAGE/$NAME"
if [[ ! -d "$APP" ]]; then
  echo "error: expected $APP after install-app.sh" >&2
  exit 2
fi

ENTITLEMENTS="$HERE/Anonymizer.entitlements"
if [[ ! -f "$ENTITLEMENTS" ]]; then
  echo "error: missing $ENTITLEMENTS" >&2
  exit 2
fi

echo "==> Signing with Developer ID + hardened runtime…"
# Timestamp requires network. --deep covers nested Mach-O (droplet binary).
codesign --force --deep --options runtime \
  --timestamp \
  --entitlements "$ENTITLEMENTS" \
  --sign "$IDENTITY" \
  "$APP"

echo "==> Verifying signature…"
codesign --verify --deep --strict --verbose=2 "$APP"
codesign -dv --verbose=2 "$APP" 2>&1 | head -25

if [[ "$SKIP_NOTARY" == "1" ]]; then
  echo "==> Skipping notarization (ANONYMIZER_SKIP_NOTARY / --skip-notary)"
else
  SUBMIT_ZIP="$STAGE/Anonymizer-submit.zip"
  echo "==> Zipping for notarytool…"
  ditto -c -k --keepParent "$APP" "$SUBMIT_ZIP"

  echo "==> Submitting to Apple notary service…"
  if [[ -n "${ANONYMIZER_API_KEY_PATH:-}" ]]; then
    : "${ANONYMIZER_API_KEY_ID:?set ANONYMIZER_API_KEY_ID with ANONYMIZER_API_KEY_PATH}"
    : "${ANONYMIZER_API_ISSUER:?set ANONYMIZER_API_ISSUER with ANONYMIZER_API_KEY_PATH}"
    xcrun notarytool submit "$SUBMIT_ZIP" \
      --key "$ANONYMIZER_API_KEY_PATH" \
      --key-id "$ANONYMIZER_API_KEY_ID" \
      --issuer "$ANONYMIZER_API_ISSUER" \
      --wait
  else
    if ! xcrun notarytool history --keychain-profile "$NOTARY_PROFILE" >/dev/null 2>&1; then
      cat >&2 <<EOF
error: notarytool profile '$NOTARY_PROFILE' not found or invalid.

One-time setup (App Store Connect API key .p8):

  xcrun notarytool store-credentials $NOTARY_PROFILE \\
    --key ~/path/to/AuthKey_XXXXXXXXXX.p8 \\
    --key-id XXXXXXXXXX \\
    --issuer XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX

Or pass:
  ANONYMIZER_API_KEY_PATH=… ANONYMIZER_API_KEY_ID=… ANONYMIZER_API_ISSUER=…

EOF
      exit 2
    fi
    xcrun notarytool submit "$SUBMIT_ZIP" \
      --keychain-profile "$NOTARY_PROFILE" \
      --wait
  fi

  echo "==> Stapling notarization ticket…"
  xcrun stapler staple "$APP"
  xcrun stapler validate "$APP"
fi

echo "==> Gatekeeper assessment…"
spctl -a -vv "$APP" 2>&1 || {
  echo "warning: spctl rejected (check notarization/staple if this is a release)" >&2
}

mkdir -p "$OUT_DIR"
OUT_ZIP="$OUT_DIR/Anonymizer-${VERSION}.zip"
rm -f "$OUT_ZIP"
echo "==> Writing $OUT_ZIP …"
ditto -c -k --keepParent "$APP" "$OUT_ZIP"

SHA="$(shasum -a 256 "$OUT_ZIP" | awk '{print $1}')"
echo
echo "✓ Release artifact ready"
echo "  zip:    $OUT_ZIP"
echo "  sha256: $SHA"
echo
echo "Next:"
echo "  1. Upload zip to GitHub Release (e.g. v${VERSION})"
echo "  2. Set cask version + sha256 in packaging/homebrew/Casks/anonymizer.rb"
echo "  3. Sync public tap: cp packaging/homebrew/Casks/anonymizer.rb \\"
echo "       \"\$(brew --repository arcane-tl/anonymizer)/Casks/\""
echo "  4. On other Mac: brew update && brew reinstall --cask anonymizer"
