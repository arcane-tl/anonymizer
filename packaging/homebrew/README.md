# Homebrew (formula + cask)

**Product name:** Anonymizer  
**CLI command:** `anonymize`  
**Finder app:** `Anonymizer.app`  

Same product, two install mechanisms (Homebrew standard):

| Install | What you get |
|---------|----------------|
| `brew install anonymizer` | CLI on PATH |
| `brew install --cask anonymizer` | **Anonymizer** in `/Applications` |

## Full Mac install (recommended)

```bash
brew tap arcane-tl/anonymizer
brew trust arcane-tl/anonymizer    # Homebrew 6+ required once
brew install anonymizer
brew install --cask anonymizer

anonymize doctor
open -a Anonymizer
```

**Important:** `anonymizer` is **not** in official `homebrew/core` or `homebrew/cask`.
You must **tap** and **trust** first.

Fully qualified form (auto-taps; still needs trust):

```bash
brew trust arcane-tl/anonymizer
brew install --cask arcane-tl/anonymizer/anonymizer
```

Tap repository: [arcane-tl/homebrew-anonymizer](https://github.com/arcane-tl/homebrew-anonymizer)

### Troubleshooting

| Error | Fix |
|-------|-----|
| `No Cask with this name exists` | `brew tap arcane-tl/anonymizer` |
| `Refusing to load … from untrusted tap` | `brew trust arcane-tl/anonymizer` (not `…/anonymize` — note the **r**) |
| Trust formula but cask still fails | Trust whole tap, or also `brew trust --cask arcane-tl/anonymizer/anonymizer` |
| App already at `/Applications/Anonymizer.app` | `brew reinstall --cask --force anonymizer` |
| **“Anonymizer is damaged and can't be opened”** | Update cask to a **notarized** build (`brew update && brew reinstall --cask anonymizer`). Interim: `xattr -cr /Applications/Anonymizer.app` then right-click → Open |
| lingua “Failed changing dylib ID” | Harmless wheel linkage warning; ignore if `anonymize --version` works |

## CLI only

```bash
brew tap arcane-tl/anonymizer
brew install anonymizer
anonymize --version
```

## GUI only note

The cask **depends on** the formula. The droplet calls `anonymize` on your PATH—install the formula first (or let the cask pull it).

## Upgrade / uninstall

```bash
brew update
brew upgrade anonymizer
brew upgrade --cask anonymizer

brew uninstall --cask anonymizer   # removes Anonymizer.app
brew uninstall anonymizer          # removes CLI
```

If `~/.local/bin/anonymize` shadows Homebrew:

```bash
brew link --overwrite anonymizer
```

## What the formula does

| Step | Behavior |
|------|----------|
| Depends | `python@3.12`; `tesseract` recommended |
| Install | venv + `pip install` + **sm** spaCy models |
| Binary | `anonymize` |

Larger models:

```bash
"$(brew --prefix anonymizer)/libexec/bin/python" -m spacy download en_core_web_lg
"$(brew --prefix anonymizer)/libexec/bin/python" -m spacy download fi_core_news_lg
```

## Developer: sync this repo → tap

```bash
# Formula
cp packaging/homebrew/anonymizer.rb \
  "$(brew --repository arcane-tl/anonymizer)/Formula/anonymizer.rb"

# Cask
mkdir -p "$(brew --repository arcane-tl/anonymizer)/Casks"
cp packaging/homebrew/Casks/anonymizer.rb \
  "$(brew --repository arcane-tl/anonymizer)/Casks/anonymizer.rb"
```

### Rebuild a **notarized** app zip (required for other Macs)

Do **not** ship a raw `install-app.sh` zip — Gatekeeper reports it as “damaged”
(unsigned / signature broken after icon plist edits).

```bash
# Prerequisites: Developer ID Application in Keychain + notarytool profile
# (see packaging/macos/README.md → Release)

./packaging/macos/release-app.sh --version 1.0.1
# → dist/Anonymizer-1.0.1.zip + sha256

# upload dist/Anonymizer-1.0.1.zip to GitHub Release v1.0.1
# set version + sha256 in Casks/anonymizer.rb, then sync tap (above)
```

## Local GUI without cask

```bash
./packaging/macos/install-app.sh --dest /Applications
# ad-hoc signed for local dev only — not for distribution
```
