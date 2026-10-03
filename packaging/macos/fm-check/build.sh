#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/anonymizer-fm-check}"
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "error: fm-check builds only on macOS" >&2
  exit 2
fi
swiftc -parse-as-library -O "$HERE/main.swift" -o "$OUT"
echo "built $OUT"
"$OUT" --available || true
