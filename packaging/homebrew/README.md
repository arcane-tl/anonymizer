# Homebrew (formula + cask)

**Product name (Finder):** Anonymizer.app  
**CLI command:** `anonymize`  

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

```bash
brew uninstall --cask anonymizer
brew install --cask anonymizer-app
brew link --overwrite anonymizer && hash -r
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
