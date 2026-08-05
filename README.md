# anonymizer

Local CLI (**macOS** + **Windows**): **PDF / DOCX / text → Markdown**, with optional PII redaction (English + Finnish). Offline by default.

> **Not a legal guarantee.** Detection is probabilistic. Always spot-check high-stakes output.

## Quick start

### Install (macOS) — Homebrew (recommended)

```bash
brew tap arcane-tl/anonymizer
brew install anonymizer

anonymize doctor
anonymize --version   # anonymizer 1.0.0
```

See [packaging/homebrew/README.md](packaging/homebrew/README.md) for PATH conflicts, models, and upgrades.
### Install (macOS) — curl installer (alternative)

```bash
curl -fsSL https://raw.githubusercontent.com/arcane-tl/anonymizer/main/scripts/install.sh | bash -s -- --yes
# New terminal (or: export PATH="$HOME/.local/bin:$PATH")
anonymize doctor
```

### Install (Windows)

```powershell
# Download and run (PowerShell)
irm https://raw.githubusercontent.com/arcane-tl/anonymizer/main/scripts/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Yes

# Or from a git clone:
.\scripts\install.ps1 -Yes -FromSource

anonymize doctor
anonymize --version
```

Default install: `%LOCALAPPDATA%\anonymizer` with `anonymize.cmd` on your user PATH.  
spaCy models default to **sm** (use `-Models lg` for large).  
Optional OCR: install [Tesseract for Windows](https://github.com/UB-Mannheim/tesseract/wiki) and put it on PATH.

Uninstall: `& "$env:LOCALAPPDATA\anonymizer\scripts\uninstall.ps1" -Yes`

### Optional Mac GUI

```bash
# Drag-and-drop app (requires anonymize on PATH — brew or curl install)
./packaging/macos/install-app.sh
```

### Use

```bash
# Full scrub (default) → contract.anonymized.md
anonymize contract.pdf

# Text only, no redaction → report.md
anonymize extract report.pdf

# Identity PII only (keeps company names)
anonymize standard sopimus.pdf

anonymize examples    # more copy-paste commands
anonymize --help

# Review redactions before writing (optional)
anonymize contract.pdf --review
# → checkbox list (all unchecked): ↑/↓ move, space toggle, enter confirm
#   checked items are kept in clear text (false positives)
anonymize contract.pdf --reject ORG_1,PHONE_2   # same without a prompt
```

| Command | What it does |
|---------|----------------|
| `anonymize FILE` | **strict** — full scrub |
| `anonymize extract FILE` | text only (no redaction) |
| `anonymize standard FILE` | people / phones / emails / IDs / addresses; keep companies |
| `anonymize strict FILE` | same as bare `anonymize FILE` |
| `anonymize doctor` | check PATH, models, OCR |

Aliases: `text` → extract · `normal` → standard · `scrub` → strict.

## Features

- **Versatile detection** — patterns, heuristics, neural NER (spaCy); optional LLM
- **No built-in company/person catalogs** — only structural rules + models + your config
- **English + Finnish**, with **auto language detection**
- **Stable placeholders**: the same person always becomes `[PERSON_1]`, etc.
- **OCR** for scanned PDFs (Tesseract + optional ocrmypdf)
- **Offline by default** — document text is not sent over the network unless you opt into remote LLM

## Security & privacy

| Mode | Document text leaves this machine? |
|------|-------------------------------------|
| Default (`anonymize file.pdf`) | **No** — local extract, spaCy, patterns only |
| `--llm` / `--llm-provider ollama` | **No**, if Ollama is on localhost (default URL) |
| `--llm --llm-provider xai` | **Yes** — text is sent to `https://api.x.ai` (requires `XAI_API_KEY`) |
| `--offline` | Blocks remote `xai` even if config enables it |

**Install-time only** network: `pip install`, `spacy download`, Homebrew OCR packages.

**Map files** (`--map`) contain original PII; written with mode `0600` on Unix when possible. Treat them like the source document.

There is **no telemetry** in this application.

## How detection works

| Layer | What it does | Signals |
|-------|----------------|---------|
| **Patterns** | Structural IDs & morphology | Email/URL shape, plate shape, 5-digit postcode with separators, hetu/Y-tunnus checksums, legal-form suffixes (`Oy`/`Ltd`/…) after capitalised name tokens |
| **Heuristics** | Orthography + POS | Multi-word Title Case / ALL CAPS; full address *shape*; spaCy POS to drop function-word glue |
| **Neural NER** | spaCy models (EN/FI) | PERSON, ORG, LOCATION (and PRODUCT→ORG) |
| **Optional LLM** | Surface extraction (`--llm`) | Model proposes entity strings; matched back into the text (`xai` or `ollama`) |
| **Your config** | Allow/deny lists | Only strings *you* put in YAML |

### Examples vs search lists

| OK | Not OK |
|----|--------|
| Synthetic strings in **tests/fixtures** to regression-test behaviour | Searching user docs for a fixed list of company/person names |
| **Few-shot examples in the LLM prompt** to teach format | Treating those teaching strings as entities to always redact |
| Structural tokens (e.g. legal form `Oy`, street ending `katu`) as *patterns* | A catalog of real suppliers hard-coded in the app |

The library does **not** ship a search list of real-world companies or people. Versatility comes from patterns, heuristics, models, and optional LLM — plus any denylist you supply.

## Install (Windows)

| Flag | Meaning |
|------|---------|
| `-Yes` | Non-interactive |
| `-FromSource` | Use current clone (editable install) |
| `-Models sm\|lg` | spaCy model size (default **sm**) |
| `-WithDev` | Also install pytest |
| `-Prefix DIR` | Install root (default `%LOCALAPPDATA%\anonymizer`) |
| `-BinDir DIR` | Launcher dir (default `%LOCALAPPDATA%\anonymizer\bin`) |
| `-Python PATH` | Specific Python 3.11+ executable |

```powershell
irm https://raw.githubusercontent.com/arcane-tl/anonymizer/main/scripts/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Yes
```

Requires **Python 3.11+** and **git** on PATH.

## Install (macOS)

### Homebrew (recommended)

See [Quick start](#quick-start) and [packaging/homebrew/README.md](packaging/homebrew/README.md).

From a clone you can also run:

```bash
./packaging/homebrew/install-local.sh
```

### curl installer (alternative)

Installs under `~/.local/share/anonymizer`, puts `anonymize` on `~/.local/bin`, optional OCR via Homebrew, spaCy models (default **lg**).

```bash
curl -fsSL https://raw.githubusercontent.com/arcane-tl/anonymizer/main/scripts/install.sh | bash -s -- --yes
```

From a git clone:

```bash
git clone https://github.com/arcane-tl/anonymizer.git
cd anonymizer
./scripts/install.sh --yes
```

| Flag | Meaning |
|------|---------|
| `--yes` | Non-interactive |
| `--no-ocr` | Skip Homebrew Tesseract/ocrmypdf |
| `--models sm` | Smaller spaCy models (faster download) |
| `--models lg` | Large models (default, better accuracy) |
| `--from-source` | Install into the current clone (dev-style) |
| `--with-dev` | Also install pytest |
| `--prefix DIR` | Install location (default `~/.local/share/anonymizer`) |

After install:

```bash
anonymize doctor
anonymize extract document.pdf
anonymize document.pdf -o clean.md
```

Upgrade:

```bash
~/.local/share/anonymizer/scripts/install.sh --yes
```

Uninstall:

```bash
~/.local/share/anonymizer/scripts/uninstall.sh --yes
```

### Manual / development install

Requires **Python 3.11+**.

```bash
# OCR (scanned PDFs)
brew install tesseract tesseract-lang ocrmypdf
tesseract --list-langs   # should include eng and fin

cd anonymizer
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download en_core_web_lg
python -m spacy download fi_core_news_lg
```

If large models are unavailable, medium/small variants are tried automatically at runtime.

## Operating modes

| Mode | Command | What it does | Default output |
|------|---------|--------------|----------------|
| **strict** | `anonymize FILE` or `anonymize strict FILE` | Full scrub — people, companies, addresses, geo, URLs, plates, Y-tunnus, VAT, … | `FILE.anonymized.md` |
| **standard** | `anonymize standard FILE` | Identity PII only — person, email, phone, hetu, addresses, IBAN, cards, IP. **Keeps** companies, Y-tunnus, VAT, URLs, countries, plates | `FILE.anonymized.md` |
| **extract** | `anonymize extract FILE` | Text only — **no redaction**. Images/logos skipped; DOCX headers/footers skipped | `FILE.md` |

Legacy flags still work: `--mode extract|standard|strict` (aliases: `text`/`plain`, `normal`/`pii`, `full`).

`--entities PERSON,EMAIL_ADDRESS,…` **overrides** the mode’s entity list. Config YAML may set `mode:` (see `config.example.yaml`).

## Usage

```bash
# Auto language detection → <stem>.anonymized.md  (strict mode)
anonymize report.pdf

# Explicit output
anonymize contract.docx -o clean.md

# Extract-only Markdown (no placeholders)
anonymize contract.docx --mode extract -o text.md

# Finnish-only NLP pass
anonymize sopimus.pdf --lang fi

# Force dual-pass (EN + FI)
anonymize mixed.pdf --lang en,fi

# Batch a folder
anonymize ./inbox/ --out-dir ./out/

# Force OCR on a scan
anonymize scan.pdf --force-ocr

# Export placeholder map (SENSITIVE — contains original PII)
anonymize report.pdf --map report.map.json

# Config: allowlist / denylist suppliers
anonymize report.pdf --config config.yaml

anonymize --list-entities
anonymize --version

# Optional LLM layer (still runs patterns + spaCy; ignored in extract mode)
anonymize doc.pdf --llm --llm-provider ollama   # fully local if Ollama is running
anonymize doc.pdf --llm --llm-provider xai      # needs XAI_API_KEY (sends text to API)
```

Install LLM client for xAI: `pip install -e ".[llm]"`.

### CLI options

| Option | Description |
|--------|-------------|
| `-m / --mode` | `extract` \| `standard` \| `strict` (default **strict**) |
| `--keep-headers` | Keep PDF page headers/footers/page numbers (default: **strip**) |
| `-r` / `--review` | Checkbox review: space to mark false positives to keep clear |
| `--no-review` | Skip review (default) |
| `--reject LIST` | Non-interactive: keep tags clear, e.g. `ORG_1,PHONE_2` |
| `-o / --output` | Output path, or `-` for stdout (single file) |
| `--out-dir` | Directory for batch outputs |
| `--lang` | `auto` (default), `en`, `fi`, or `en,fi` |
| `--entities` | Comma-separated entity types (**overrides mode**) |
| `--score-threshold` | Min NER confidence (default `0.5`) |
| `--include-dates` | Also redact dates (standard/strict) |
| `--force-ocr` / `--no-ocr` | OCR control for PDFs |
| `--map` | Write placeholder → original JSON (**PII**) |
| `--config` | YAML config (see `config.example.yaml`) |
| `--llm` | Enable optional LLM entity layer (default provider: **ollama**) |
| `--llm-provider` | `ollama` (local) or `xai` (remote — sends text) |
| `--llm-model` | Model name override |
| `--offline` | Forbid remote `xai` LLM |
| `-q` / `--quiet` | Hide step-by-step progress (stderr) |

Progress (elapsed timer + pipeline steps) is printed to **stderr** so Markdown on stdout (`-o -`) stays clean.

## What gets redacted

Depends on **mode** (see table above). In **strict** (default):

| Type | Placeholder |
|------|-------------|
| Person names | `[PERSON_n]` |
| Organizations / suppliers / providers | `[ORG_n]` |
| Email | `[EMAIL_n]` |
| Phone (incl. Finnish `+358` / `040…`) | `[PHONE_n]` |
| Street + house (structured) | `[STREET_n]` |
| City / locality (with postcode pattern) | `[CITY_n]` |
| Finnish postal code | `[POSTAL_n]` |
| Other geo (spaCy residual) | `[LOCATION_n]` |
| Webpage URLs (`https://…`, `www.…`) | `[URL_n]` |
| Finnish registration plate (`ABC-123`) | `[PLATE_FI_n]` |
| Vehicle VIN / valmistenumero (17-char, **strict** only) | `[VIN_n]` |
| Finnish henkilötunnus | `[FI_HETU_n]` |
| Finnish Y-tunnus | `[FI_BUSINESS_ID_n]` |
| Finnish ALV / VAT (`FI` + 8 digits) | `[VAT_FI_n]` |
| Company names (`… Oy`, `… Ltd`, …) | `[ORG_n]` |
| IBAN, credit card, IP | `[IBAN_n]`, … |

Dates are **off** by default (`--include-dates` to enable).

## Language behaviour

1. Extract text (OCR with `eng+fin` when auto and the PDF text layer is thin).
2. Detect language with **lingua** (EN + FI only).
3. Run spaCy/Presidio for `en`, `fi`, or both if mixed / low confidence.
4. Always run pattern recognizers (email, phone, IBAN, hetu, Y-tunnus).
5. Replace with stable placeholders; write Markdown + YAML front matter.

## Privacy

- All processing is local.
- Do not commit `*.map.json` or real customer documents.
- The optional `--map` file **contains original PII** — treat it like the source document.

## Development

```bash
source .venv/bin/activate
pytest
```

### Contract & realworld regression

```bash
# Synthetic contracts (recall: PII must be gone)
pytest tests/test_contract_templates.py -q

# Realworld-style EN/FI docs (precision: boilerplate must survive)
pytest tests/test_realworld_precision.py tests/test_offline_security.py -q

# Manual
anonymize tests/fixtures/contract_en.txt -o /tmp/en.md --lang en
anonymize tests/fixtures/realworld/fi_sample_sopimus.txt -o /tmp/fi.md --lang fi
```

See `tests/fixtures/README.md` and `tests/fixtures/realworld/SOURCES.md`.

OCR and spaCy-heavy tests may skip if models or Tesseract are missing.

## License

MIT — see [LICENSE](LICENSE).
