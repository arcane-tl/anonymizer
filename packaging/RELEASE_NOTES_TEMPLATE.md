# Release notes template

Use when creating a GitHub Release (tag `vX.Y.Z`). Attach **all** platform assets before publishing.

## Assets (required naming)

| File | Platform |
|------|----------|
| `Anonymizer-X.Y.Z.zip` | macOS Anonymizer.app (notarized when possible) |
| `Anonymizer-Setup-X.Y.Z.exe` | Windows Setup (Apps & features) |
| `Anonymizer-X.Y.Z-windows.zip` | Windows portable (optional but recommended) |
| Source tarball (auto) | Homebrew formula |

## Body (copy and fill)

```markdown
## Install

### macOS
```bash
brew update && brew upgrade anonymizer anonymizer-app
# or: download **Anonymizer-X.Y.Z.zip** from this release → Applications
```

### Windows
1. Download **Anonymizer-Setup-X.Y.Z.exe** (recommended)
2. Run the wizard → Start Menu **Anonymizer**
3. Uninstall: **Settings → Apps → Anonymizer**

Portable: **Anonymizer-X.Y.Z-windows.zip** (keep the `runtime\` folder next to `Anonymizer.exe`).

### CLI
- macOS: `anonymize` via Homebrew formula  
- Windows: optional “Add CLI to PATH” in Setup → `anonymize`

## What's new

- …
```

## Checklist

- [ ] `pyproject.toml` version = tag without `v`
- [ ] Mac app notarized + stapled
- [ ] Windows Setup built and smoke-tested (Apps list + uninstall)
- [ ] Homebrew formula + cask sha256 updated
- [ ] Release body includes **Install** for Mac **and** Windows
