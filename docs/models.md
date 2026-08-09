# spaCy models: defaults, switching size, and extra languages

Anonymizer uses **spaCy** for neural NER (people, organisations, places).  
**Structural detectors** (Finnish hetu / Y-tunnus / plates / VAT, emails, phones, IBAN, VIN, URLs, street patterns) do **not** depend on model size.

## Default install (quality-first)

Installers ensure **English + Finnish large** models via:

```bash
python -m anonymizer.install_models --langs en,fi --size lg --fallback
```

**Precheck:** if models already load, installers **skip download** and print that they are ready (safe to re-run; no reinstall needed). If `anonymize doctor` is green for EN+FI, you can ignore older brew “model install” warnings.

| Language | Default package |
|----------|-----------------|
| English | `en_core_web_lg` |
| Finnish | `fi_core_news_lg` |

| Channel | How to choose size |
|---------|-------------------|
| macOS/Linux `install.sh` | `--models lg` (default), `md`, or `sm` |
| Windows `install.ps1` | `-Models lg` (default), `md`, or `sm` |
| Homebrew | post-install runs `install_models` for **lg** EN+FI |
| Windows Setup build | `-Models lg` (default); use `sm` for a smaller artifact |

First install with **lg** can take several minutes and roughly **600–700 MB** of model data for EN+FI combined. That is intentional: better PERSON/ORG detection out of the box.

Runtime resolution (when several sizes are installed): **lg → md → sm** for each language (see `SPACY_MODELS` / `SPACY_FALLBACKS` in `config.py`).

## Switch model size or reinstall models

Use the **same Python** that runs `anonymize` (venv, Homebrew libexec, or Windows `runtime\python.exe`).

```bash
# Preferred size (lg = best quality, sm = smaller/faster)
python -m anonymizer.install_models --langs en,fi --size lg --fallback
python -m anonymizer.install_models --langs en,fi --size sm
python -m anonymizer.install_models --check
```

**Homebrew** (formula’s own Python — do not use bare system `pip install en_core_web_lg`):

```bash
brew postinstall anonymizer
# or:
"$(brew --prefix anonymizer)/libexec/bin/python" -m anonymizer.install_models \
  --langs en,fi --size lg --fallback
```

**Windows** (user install from `install.ps1`):

```powershell
& "$env:LOCALAPPDATA\Anonymizer\.venv\Scripts\python.exe" -m anonymizer.install_models --langs en,fi --size sm
```

**Windows Setup / portable** (embedded runtime):

```powershell
& ".\runtime\python.exe" -m anonymizer.install_models --langs en,fi --size sm
```

You do **not** need to reinstall the app. Installing a smaller model does not remove a larger one; the app prefers the largest available unless you override config (below).

## Add languages (optional)

Swedish is supported in the pipeline (`--lang sv`) but **not** installed by default.

```bash
python -m anonymizer.install_models --langs sv --size lg
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

Or only re-download models with `python -m anonymizer.install_models …` as above (preferred).
