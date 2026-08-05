# Homebrew formula

Install **anonymizer** (`anonymize` CLI) with Homebrew on macOS.

## Public install (recommended)

```bash
brew tap arcane-tl/anonymizer
brew install anonymizer

anonymize doctor
anonymize --version   # → anonymizer 1.0.0
```

Tap repository: [arcane-tl/homebrew-anonymizer](https://github.com/arcane-tl/homebrew-anonymizer)  
(`brew tap arcane-tl/anonymizer` maps to that repo by Homebrew convention.)

### Upgrade / uninstall

```bash
brew update
brew upgrade anonymizer
brew uninstall anonymizer
```

If an older curl install left `~/.local/bin/anonymize` ahead of Homebrew on `PATH`:

```bash
brew link --overwrite anonymizer
# or put /opt/homebrew/bin before ~/.local/bin
```

## What the formula does

| Step | Behavior |
|------|----------|
| Depends | `python@3.12`; `tesseract` recommended |
| Install | venv in the Cellar + `pip install` of this project **and** PyPI deps |
| Binary | `anonymize` on PATH |
| post_install | Downloads **en_core_web_sm** and **fi_core_news_sm** |
| Version | **1.0.0** (tag `v1.0.0`) |

For higher accuracy (larger models):

```bash
"$(brew --prefix anonymizer)/libexec/bin/python" -m spacy download en_core_web_lg
"$(brew --prefix anonymizer)/libexec/bin/python" -m spacy download fi_core_news_lg
```

Optional OCR: `brew install tesseract tesseract-lang ocrmypdf`

## Developer / monorepo workflow

Formula source of truth in this repo: `packaging/homebrew/anonymizer.rb`  
(copy into the public tap when releasing).

```bash
# From a clone, install without using the public tap:
./packaging/homebrew/install-local.sh

# HEAD of main (after tap formula exists):
brew install --HEAD arcane-tl/anonymizer/anonymizer
```

### Refresh sha256 for a new tag

```bash
git tag -a vX.Y.Z -m "…"
git push origin vX.Y.Z
curl -sL "https://github.com/arcane-tl/anonymizer/archive/refs/tags/vX.Y.Z.tar.gz" | shasum -a 256
# update packaging/homebrew/anonymizer.rb and the public tap Formula/anonymizer.rb
```

## Mac GUI droplet

Formula installs the **CLI only**. Drag-and-drop:

```bash
git clone https://github.com/arcane-tl/anonymizer.git
cd anonymizer && ./packaging/macos/install-app.sh
```

## Offline note

`post_install` needs network for spaCy models. If it fails:

```bash
"$(brew --prefix anonymizer)/libexec/bin/python" -m spacy download en_core_web_sm
"$(brew --prefix anonymizer)/libexec/bin/python" -m spacy download fi_core_news_sm
```
