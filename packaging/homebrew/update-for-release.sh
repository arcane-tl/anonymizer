#!/usr/bin/env bash
# Update formula + cask version/url/sha256 for a release.
# Usage:
#   ./packaging/homebrew/update-for-release.sh \
#     --version 1.1.1 \
#     --source-sha <sha256 of vX.Y.Z.tar.gz> \
#     --cask-sha <sha256 of Anonymizer-X.Y.Z.zip>
#
# Version defaults to scripts/version.sh (pyproject.toml).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION=""
SOURCE_SHA=""
CASK_SHA=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --source-sha) SOURCE_SHA="$2"; shift 2 ;;
    --cask-sha) CASK_SHA="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,20p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  VERSION="$("$ROOT/scripts/version.sh")"
fi
if [[ -z "$SOURCE_SHA" || -z "$CASK_SHA" ]]; then
  echo "error: --source-sha and --cask-sha are required" >&2
  exit 2
fi

FORMULA="$ROOT/packaging/homebrew/anonymizer.rb"
CASK="$ROOT/packaging/homebrew/Casks/anonymizer.rb"

python3 - <<PY
from pathlib import Path
import re

version = """$VERSION"""
source_sha = """$SOURCE_SHA"""
cask_sha = """$CASK_SHA"""

def sub_field(text: str, key: str, value: str) -> str:
    # version "x", sha256 "x"
    return re.sub(
        rf'^(\s*{re.escape(key)}\s+")[^"]*(")',
        rf'\g<1>{value}\g<2>',
        text,
        count=1,
        flags=re.M,
    )

# Formula
ft = Path(r"""$FORMULA""").read_text(encoding="utf-8")
ft = re.sub(
    r'url "https://github.com/arcane-tl/anonymizer/archive/refs/tags/v[^"]+\.tar\.gz"',
    f'url "https://github.com/arcane-tl/anonymizer/archive/refs/tags/v{version}.tar.gz"',
    ft,
    count=1,
)
ft = sub_field(ft, "sha256", source_sha)
ft = sub_field(ft, "version", version)
Path(r"""$FORMULA""").write_text(ft, encoding="utf-8")

# Cask
ct = Path(r"""$CASK""").read_text(encoding="utf-8")
ct = sub_field(ct, "version", version)
ct = sub_field(ct, "sha256", cask_sha)
Path(r"""$CASK""").write_text(ct, encoding="utf-8")

print(f"Updated formula + cask to {version}")
print(f"  source sha256: {source_sha}")
print(f"  cask   sha256: {cask_sha}")
PY
