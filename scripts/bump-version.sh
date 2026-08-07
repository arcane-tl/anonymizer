#!/usr/bin/env bash
# Set [project].version in pyproject.toml (canonical version source).
# Usage:
#   ./scripts/bump-version.sh 1.1.1
# Does not commit. Optionally updates README marker:
#   <!-- ANONYMIZER_VERSION -->…<!-- /ANONYMIZER_VERSION -->

set -euo pipefail

NEW="${1:-}"
if [[ -z "$NEW" || ! "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-].*)?$ ]]; then
  echo "usage: $0 X.Y.Z" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYPROJECT="$ROOT/pyproject.toml"

python3 - <<PY
from pathlib import Path
import re
path = Path(r"""$PYPROJECT""")
text = path.read_text(encoding="utf-8")
new = """$NEW"""
# Replace first version = "..." under [project] region (simple, reliable for our file)
pat = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.M)
m = pat.search(text)
if not m:
    raise SystemExit("error: version = \"...\" not found in pyproject.toml")
text2, n = pat.subn(rf'\g<1>{new}\g<3>', text, count=1)
if n != 1:
    raise SystemExit("error: failed to replace version")
path.write_text(text2, encoding="utf-8")
print(f"pyproject.toml version -> {new}")
PY

README="$ROOT/README.md"
if [[ -f "$README" ]] && grep -q 'ANONYMIZER_VERSION' "$README"; then
  # Portable in-place replace for marker pair
  python3 - <<PY
from pathlib import Path
import re
path = Path(r"""$README""")
text = path.read_text(encoding="utf-8")
new = """$NEW"""
text2, n = re.subn(
    r"(<!-- ANONYMIZER_VERSION -->)(.*?)(<!-- /ANONYMIZER_VERSION -->)",
    rf"\g<1>{new}\g<3>",
    text,
    count=1,
    flags=re.S,
)
if n:
    path.write_text(text2, encoding="utf-8")
    print(f"README version marker -> {new}")
PY
fi

echo "Next: commit, tag v$NEW, ./packaging/macos/release-app.sh, packaging/homebrew/update-for-release.sh"
