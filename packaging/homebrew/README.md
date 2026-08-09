# Homebrew (formula + cask) — macOS

**Product name (Finder):** Anonymizer.app  
**CLI command:** `anonymize`  

For **Windows** (Setup.exe, Apps & features uninstall), see [../windows/README.md](../windows/README.md).

| Package | Token | What you get |
|---------|--------|----------------|
| Formula | `anonymizer` | CLI on PATH |
| Cask | `anonymizer-app` | **Anonymizer.app** in `/Applications` |

Different tokens on purpose: if formula and cask share a name, Homebrew **skips linking** the CLI (`cask is installed, skipping link`).

## Full Mac install (one command)

```bash
brew tap arcane-tl/anonymizer
brew trust arcane-tl/anonymizer    # Homebrew 6+ required once
brew install --cask anonymizer-app # pulls formula + installs app

anonymize doctor
open -a Anonymizer
```

**Important:** not in official `homebrew/core` / `homebrew/cask` — tap + trust first.

Tap: [arcane-tl/homebrew-anonymizer](https://github.com/arcane-tl/homebrew-anonymizer)

### Troubleshooting

| Error / symptom | Fix |
|-----------------|-----|
| `No Cask with this name exists` | `brew tap arcane-tl/anonymizer` |
| Untrusted tap | `brew trust arcane-tl/anonymizer` |
| `command not found: anonymize` after cask install | Old cask token conflict: see migration below |
| `anonymizer cask is installed, skipping link` | `brew uninstall --cask anonymizer` then `brew link --overwrite anonymizer` |
| App “damaged” | `brew reinstall --cask anonymizer-app` or `xattr -cr /Applications/Anonymizer.app` |
| `--review-window` / app Review: needs tkinter | `brew install python-tk@3.12` then retry (formula depends on it from 1.3.1+) |
| lingua dylib ID warning | Harmless; ignore if CLI works |

## CLI only

```bash
brew install anonymizer
anonymize --version
```

## Upgrade / reinstall / uninstall

```bash
brew update
brew upgrade anonymizer anonymizer-app

brew reinstall anonymizer anonymizer-app
brew link --overwrite anonymizer && hash -r

brew uninstall --cask anonymizer-app
brew uninstall anonymizer
```

## Migration from cask token `anonymizer` → `anonymizer-app`

The old cask token is **gone from the tap**. Uninstall may need `--force` or a manual Caskroom cleanup:

```bash
# 1) Remove old cask (try force if plain uninstall errors)
brew uninstall --cask --force anonymizer

# If you still see errors about Caskroom/.../Anonymizer.app:
rm -rf "$(brew --prefix)/Caskroom/anonymizer"
rm -rf /Applications/Anonymizer.app

# 2) Install new cask + ensure CLI is linked
brew install --cask anonymizer-app
brew reinstall anonymizer          # optional if already installed
brew link --overwrite anonymizer
hash -r

anonymize --version
open -a Anonymizer
```

## Developer: sync monorepo → tap

```bash
cp packaging/homebrew/anonymizer.rb \
  "$(brew --repository arcane-tl/anonymizer)/Formula/anonymizer.rb"
mkdir -p "$(brew --repository arcane-tl/anonymizer)/Casks"
cp packaging/homebrew/Casks/anonymizer-app.rb \
  "$(brew --repository arcane-tl/anonymizer)/Casks/anonymizer-app.rb"
# remove obsolete same-name cask if present:
rm -f "$(brew --repository arcane-tl/anonymizer)/Casks/anonymizer.rb"
```

Release helper:

```bash
./packaging/homebrew/update-for-release.sh \
  --version X.Y.Z \
  --source-sha <tarball> \
  --cask-sha <Anonymizer-X.Y.Z.zip>
```

## Local GUI without cask

```bash
./packaging/macos/install-app.sh --dest /Applications
```
