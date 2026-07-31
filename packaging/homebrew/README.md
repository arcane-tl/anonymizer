# Homebrew formula

Install **anonymizer** (`anonymize` CLI) with Homebrew on macOS.

> **Note:** Modern Homebrew requires formulae to live in a **tap**, not a bare
> file path (`brew install ./foo.rb` is rejected).

## Install from this repository

```bash
# 1) Create a local tap once (if you do not already have arcane-tl/anonymizer)
brew tap-new --no-git arcane-tl/anonymizer 2>/dev/null || true
# if tap-new fails mid-way, the Formula directory may still exist under:
#   $(brew --repository arcane-tl/anonymizer)/Formula

# 2) Copy / update the formula from the monorepo
cp packaging/homebrew/anonymizer.rb \
  "$(brew --repository arcane-tl/anonymizer)/Formula/anonymizer.rb"

# 3a) Development / latest main (no GitHub tag required):
#     Edit the formula head branch if needed, then:
brew install --HEAD arcane-tl/anonymizer/anonymizer

# 3b) After v1.0.0 is tagged and sha256 is filled in anonymizer.rb:
brew install arcane-tl/anonymizer/anonymizer

anonymize doctor
anonymize --version   # → anonymizer 1.0.0
```

If an older curl install left `~/.local/bin/anonymize` ahead of Homebrew on
`PATH`, either reorder PATH or:

```bash
brew link --overwrite anonymizer
```

## What the formula does

| Step | Behavior |
|------|----------|
| Depends | `python@3.12`; `tesseract` recommended |
| Install | venv in the Cellar + `pip install` of this project **and** PyPI deps |
| Binary | `anonymize` on PATH (symlink) |
| post_install | Downloads **en_core_web_sm** and **fi_core_news_sm** |
| Version | **1.0.0** |

The curl/`install.sh` path can still use large models; brew defaults to **sm** for a quicker first install.

## Upgrade / uninstall

```bash
# After updating the formula file in the tap:
brew reinstall arcane-tl/anonymizer/anonymizer
# or HEAD:
brew reinstall --HEAD arcane-tl/anonymizer/anonymizer

brew uninstall anonymizer
```

## Refresh sha256 after tagging v1.0.0

```bash
git tag -a v1.0.0 -m "anonymizer 1.0.0"
git push origin v1.0.0

curl -sL https://github.com/arcane-tl/anonymizer/archive/refs/tags/v1.0.0.tar.gz \
  | shasum -a 256
# paste into packaging/homebrew/anonymizer.rb as sha256 "…"
# re-copy formula into the tap and: brew upgrade / reinstall
```

## Future: public tap

```bash
brew tap arcane-tl/anonymizer   # when github.com/arcane-tl/homebrew-anonymizer exists
brew install anonymizer
```

Until then, use the monorepo formula + local tap steps above.

## Mac GUI droplet

The formula installs the **CLI only**. For drag-and-drop:

```bash
./packaging/macos/install-app.sh
```

`anonymize` must be on `PATH` (brew provides this).

## Offline note

`post_install` needs network for spaCy model downloads. If it fails:

```bash
"$(brew --prefix anonymizer)/libexec/bin/python" -m spacy download en_core_web_sm
"$(brew --prefix anonymizer)/libexec/bin/python" -m spacy download fi_core_news_sm
```
