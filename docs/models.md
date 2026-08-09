# spaCy models: defaults, switching size, and extra languages

Anonymizer uses **spaCy** for neural NER (people, organisations, places).  
**Structural detectors** (Finnish hetu / Y-tunnus / plates / VAT, emails, phones, IBAN, VIN, URLs, street patterns) do **not** depend on model size.

## Default install (quality-first)

Installers download **English + Finnish large** models by default:

| Language | Default package |
|----------|-----------------|
| English | `en_core_web_lg` |
| Finnish | `fi_core_news_lg` |

| Channel | How to choose size |
|---------|-------------------|
| macOS/Linux `install.sh` | `--models lg` (default), `md`, or `sm` |
| Windows `install.ps1` | `-Models lg` (default), `md`, or `sm` |
| Homebrew | post-install pulls **lg** EN+FI |
| Windows Setup build | `-Models lg` (default); use `sm` for a smaller artifact |

First install with **lg** can take several minutes and roughly **600–700 MB** of model data for EN+FI combined. That is intentional: better PERSON/ORG detection out of the box.

Runtime resolution (when several sizes are installed): **lg → md → sm** for each language (see `SPACY_MODELS` / `SPACY_FALLBACKS` in `config.py`).

## Switch model size (after install)

Use the **same Python** that runs `anonymize` (venv, Homebrew libexec, or Windows `runtime\python.exe`).

### Smaller / faster

```bash
python -m spacy download en_core_web_sm
python -m spacy download fi_core_news_sm
```

### Medium (balance)

```bash
python -m spacy download en_core_web_md
python -m spacy download fi_core_news_md
```

### Large (best classic NER — default)

```bash
python -m spacy download en_core_web_lg
python -m spacy download fi_core_news_lg
```

**Homebrew** — do **not** use bare `pip install en_core_web_lg` (models are not on PyPI under that name). Prefer:

```bash
# Re-run formula post_install (resolves correct GitHub wheels for your spaCy version)
brew update
brew reinstall anonymizer
# or:
brew postinstall anonymizer
```

Manual wheel install (example for **spaCy 3.8.x** — check `anonymize doctor` / spaCy version if this 404s):

```bash
HOST_PY="$(brew --prefix python@3.12)/libexec/bin/python"
VENV_PY="$(brew --prefix anonymizer)/libexec/bin/python"
"$HOST_PY" -m pip --python="$VENV_PY" install --upgrade \
  https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl \
  https://github.com/explosion/spacy-models/releases/download/fi_core_news_lg-3.8.0/fi_core_news_lg-3.8.0-py3-none-any.whl

# Optional Swedish
"$HOST_PY" -m pip --python="$VENV_PY" install \
  https://github.com/explosion/spacy-models/releases/download/sv_core_news_lg-3.8.0/sv_core_news_lg-3.8.0-py3-none-any.whl
```

**Windows** (user install from `install.ps1`):

```powershell
& "$env:LOCALAPPDATA\Anonymizer\.venv\Scripts\python.exe" -m spacy download en_core_web_sm
```

**Windows Setup / portable** (embedded runtime):

```powershell
& ".\runtime\python.exe" -m spacy download en_core_web_sm
```

You do **not** need to reinstall the app. Installing a smaller model does not remove a larger one; the app prefers the largest available unless you override config (below).

## Add languages (optional)

Swedish is supported in the pipeline (`--lang sv`) but **not** installed by default.

```bash
python -m spacy download sv_core_news_lg   # or _md / _sm
anonymize document.pdf --lang sv
anonymize document.pdf --lang en,sv        # mixed
```

Verify:

```bash
anonymize doctor
```

Doctor treats **en** and **fi** as required and **sv** as optional.

Norwegian/Danish can follow the same pattern later (install spaCy model + use `--lang` once wired).

## Force a specific package (config)

```yaml
# config.yaml
spacy_models:
  en: en_core_web_md
  fi: fi_core_news_md
  # sv: sv_core_news_lg
```

```bash
anonymize doc.pdf --config config.yaml
```

## What size means for quality

| Size | Vectors | Typical use |
|------|---------|-------------|
| **sm** | none | Small install, faster load, slightly weaker NER |
| **md** | reduced | Good balance |
| **lg** | full | **Best PERSON/ORG quality** (recommended default) |

IDs and form patterns work the same on all sizes. For more detail on custom entity patterns, see [plugins.md](plugins.md).

## Re-run installers with a different size

```bash
# macOS/Linux clone
./scripts/install.sh --yes --from-source --models sm

# Windows clone
.\scripts\install.ps1 -Yes -FromSource -Models sm
```

Or only re-download models with `python -m spacy download …` as above (preferred).
