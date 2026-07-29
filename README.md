# anonymizer

Local Mac CLI that anonymizes documents (PDF, DOCX, plain text) by removing personal and business identifiers, then writes **Markdown**.

- **Offline** after models and system OCR deps are installed (no cloud APIs)
- **English + Finnish**, with **auto language detection**
- **Stable placeholders**: the same person always becomes `[PERSON_1]`, etc.
- **OCR** for scanned PDFs (Tesseract + optional ocrmypdf)

> **Not a legal guarantee.** NER is probabilistic. Always spot-check high-stakes output.

## Install (macOS)

### System dependencies (OCR)

```bash
brew install tesseract tesseract-lang ocrmypdf
tesseract --list-langs   # should include eng and fin
```

### Python package

Requires **Python 3.11+**.

```bash
cd anonymizer
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# spaCy models (large preferred)
python -m spacy download en_core_web_lg
python -m spacy download fi_core_news_lg
```

If large models are unavailable, medium/small variants are tried automatically.

## Usage

```bash
# Auto language detection → <stem>.anonymized.md
anonymize report.pdf

# Explicit output
anonymize contract.docx -o clean.md

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
```

### CLI options

| Option | Description |
|--------|-------------|
| `-o / --output` | Output path, or `-` for stdout (single file) |
| `--out-dir` | Directory for batch outputs |
| `--lang` | `auto` (default), `en`, `fi`, or `en,fi` |
| `--entities` | Comma-separated entity types |
| `--score-threshold` | Min NER confidence (default `0.5`) |
| `--include-dates` | Also redact dates |
| `--force-ocr` / `--no-ocr` | OCR control for PDFs |
| `--map` | Write placeholder → original JSON (**PII**) |
| `--config` | YAML config (see `config.example.yaml`) |

## What gets redacted

| Type | Placeholder |
|------|-------------|
| Person names | `[PERSON_n]` |
| Organizations / suppliers / providers | `[ORG_n]` |
| Email | `[EMAIL_n]` |
| Phone | `[PHONE_n]` |
| Location | `[LOCATION_n]` |
| Finnish henkilötunnus | `[FI_HETU_n]` |
| Finnish Y-tunnus | `[FI_BUSINESS_ID_n]` |
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

OCR and spaCy-heavy tests may skip if models or Tesseract are missing.

## License

MIT — see [LICENSE](LICENSE).
