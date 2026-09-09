#!/usr/bin/env bash
# Sync monorepo packaging/homebrew → public tap Formula/ + Casks/.
# Usage (from repo root or this directory):
#   ./packaging/homebrew/sync-tap.sh
#   ./packaging/homebrew/sync-tap.sh --commit "anonymizer 1.4.6"
#
# Homebrew loads Formula/anonymizer.rb — never leave a root anonymizer.rb in the tap.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TAP_NAME="${HOMEBREW_ANONYMIZER_TAP:-arcane-tl/anonymizer}"
DO_COMMIT=0
COMMIT_MSG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --commit)
      DO_COMMIT=1
      COMMIT_MSG="${2:-}"
      shift 2
      ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if ! command -v brew >/dev/null 2>&1; then
  echo "error: brew not found" >&2
  exit 2
fi

if ! TAP="$(brew --repository "$TAP_NAME" 2>/dev/null)"; then
  echo "error: tap not found: $TAP_NAME (brew tap arcane-tl/anonymizer)" >&2
  exit 2
fi

mkdir -p "$TAP/Formula" "$TAP/Casks"
cp "$ROOT/packaging/homebrew/anonymizer.rb" "$TAP/Formula/anonymizer.rb"
cp "$ROOT/packaging/homebrew/Casks/anonymizer-app.rb" "$TAP/Casks/anonymizer-app.rb"
# Homebrew loads Formula/ and Casks/ only
rm -f "$TAP/anonymizer.rb" "$TAP/Casks/anonymizer.rb"

echo "Synced → $TAP"
echo "  Formula/anonymizer.rb"
echo "  Casks/anonymizer-app.rb"

if [[ "$DO_COMMIT" -eq 1 ]]; then
  if [[ -z "$COMMIT_MSG" ]]; then
    ver="$(grep -E '^\s*version "' "$ROOT/packaging/homebrew/anonymizer.rb" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')"
    COMMIT_MSG="anonymizer ${ver}"
  fi
  cd "$TAP"
  git add Formula/anonymizer.rb Casks/anonymizer-app.rb
  git add -u anonymizer.rb Casks/anonymizer.rb 2>/dev/null || true
  if git diff --cached --quiet; then
    echo "Nothing to commit in tap."
  else
    git commit -m "$COMMIT_MSG"
    echo "Committed in tap. Push with: git -C \"$TAP\" push origin HEAD"
  fi
fi
