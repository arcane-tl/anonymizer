#!/usr/bin/env bash
# Print the package version from pyproject.toml (canonical source of truth).
# Usage (from anywhere):
#   scripts/version.sh
# Override for emergency rebuilds only:
#   ANONYMIZER_VERSION=1.2.3 scripts/version.sh

set -euo pipefail

if [[ -n "${ANONYMIZER_VERSION:-}" ]]; then
  printf '%s\n' "$ANONYMIZER_VERSION"
  exit 0
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYPROJECT="$ROOT/pyproject.toml"
if [[ ! -f "$PYPROJECT" ]]; then
  echo "error: pyproject.toml not found at $PYPROJECT" >&2
  exit 2
fi

python3 -c "
import tomllib
from pathlib import Path
data = tomllib.loads(Path(r'''$PYPROJECT''').read_text(encoding='utf-8'))
print(data['project']['version'])
"
