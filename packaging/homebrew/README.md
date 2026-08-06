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
brew install anonymizer
brew install --cask anonymizer

anonymize doctor
open -a Anonymizer
```

Tap repository: [arcane-tl/homebrew-anonymizer](https://github.com/arcane-tl/homebrew-anonymizer)

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

Rebuild the app zip for a new version:

```bash
./packaging/macos/install-app.sh --dest /tmp/anon-stage
ditto -c -k --sequesterRsrc --keepParent \
  /tmp/anon-stage/Anonymizer.app /tmp/Anonymizer-VERSION.zip
shasum -a 256 /tmp/Anonymizer-VERSION.zip
# upload to GitHub Release; update sha256 in Casks/anonymizer.rb
```

## Local GUI without cask

```bash
./packaging/macos/install-app.sh --dest /Applications
```
