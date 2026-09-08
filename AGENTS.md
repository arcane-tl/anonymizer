# AGENTS.md — guidance for coding agents on **anonymizer**

Local CLI (macOS + Windows) that turns **PDF / DOCX / plain text → Markdown**, with optional PII redaction for **English + Finnish**, optional **native PDF/DOCX** output, and thin GUIs. Offline by default. Package version: see `pyproject.toml` / `anonymizer.__version__` (currently **1.4.5** on branch).

This file is **local-only** (listed in `.gitignore`). Prefer project conventions here over generic agent defaults when they conflict.

---

## What this project is / is not

| Is | Is not |
|----|--------|
| Local document de-identification tool | A legal guarantee of complete redaction |
| Pattern + spaCy NER + optional LLM | Hard-coded catalogs of real companies/people |
| EN + FI focused | Full multi-language coverage |
| CLI (`anonymize`) first; GUIs call CLI | A library-first public API (internal modules may change) |

**Never** commit real customer PDFs, map files, or anonymized outputs that still contain residual PII. Synthetic fixtures and public samples only.

---

## Repository layout

```text
anonymizer/
├── pyproject.toml
├── config.example.yaml
├── README.md
├── Makefile
├── scripts/                # install.sh (macOS), install.ps1 (Windows), version
├── packaging/
│   ├── macos/              # AppleScript droplet, run-anonymize.sh, release-app.sh
│   ├── windows/            # GUI freeze, Inno Setup, build-release.ps1
│   └── homebrew/
├── src/anonymizer/
│   ├── cli.py              # Typer entry: run() rewrites CLI verbs
│   ├── lists_io.py         # legacy allow/deny YAML helpers + config path
│   ├── templates_io.py     # machine-readable templates bridge (Mac GUI shell)
│   ├── gui/                # tkinter options (Win) + review_window (both)
│   ├── anonymize/
│   │   ├── config.py, engine.py, mapping.py, language.py, review.py
│   │   ├── templates.py, domain_lexicon.py, org_stems.py, llm.py, recognizers/
│   ├── extract/            # PDF / DOCX / text + OCR
│   ├── output/             # markdown.py, native.py, pdf_redact, docx_redact
│   ├── templates/builtin/  # shipped allow/deny packs
│   └── util/
└── tests/
```

Entrypoints: `anonymize = anonymizer.cli:run`, `anonymize-gui = anonymizer.gui:main`.

---

## Dependencies (runtime)

From `pyproject.toml` (Python **≥3.11**):

| Package | Role |
|---------|------|
| `presidio-analyzer` / `presidio-anonymizer` | Pattern registry + analyze API |
| `spacy` | Neural NER (EN/FI models installed separately) |
| `python-docx` | DOCX extract |
| `pymupdf` | PDF text extract |
| `typer` + `rich` | CLI / progress / tables |
| `questionary` | `--review` checkbox UI (prompt_toolkit) |
| `pyyaml` | config + MD front matter |
| `lingua-language-detector` | language detection |

Optional extras:

- `.[dev]` → `pytest`, `pytest-cov`
- `.[llm]` → `openai` (xAI-compatible client)

**System (macOS, optional OCR):** Tesseract (+ `fin`/`eng`), ocrmypdf — via Homebrew in `install.sh`.

**spaCy models (required for NER):**  
`en_core_web_lg` / `fi_core_news_lg` (fallback `md`/`sm`). Resolved in `config.SPACY_MODELS` / `SPACY_FALLBACKS`.

Do **not** vendor models into the repo (`models/` is gitignored).

---

## Environment & commands

```bash
# Dev from clone
./scripts/install.sh --yes --from-source --with-dev
# or
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download en_core_web_lg
python -m spacy download fi_core_news_lg

# Tests
make test
# or: . .venv/bin/activate && pytest -q

# CLI (after install: ~/.local/bin/anonymize)
anonymize doctor
anonymize --version
anonymize path/to.pdf
anonymize extract path/to.pdf
anonymize standard path/to.pdf --review
```

Use project `.venv` for development. Do not commit `.venv/`.

---

## Operating modes (entity presets)

Defined in `anonymize/config.py`:

| Mode | CLI | Redacts | Skips |
|------|-----|---------|--------|
| **strict** (default) | `anonymize FILE` / `strict` | Full scrub: people, orgs, geo, URLs, plates, VAT, VIN, … | — |
| **standard** | `anonymize standard FILE` | Identity: person, contact, IDs, addresses, IBAN, IP | ORG, LOCATION countries, Y-tunnus/VAT, URL, plate, VIN |
| **extract** | `anonymize extract FILE` | Nothing (text → MD only) | All detection |

Aliases rewritten in `cli.run()`: `text`/`plain`→extract, `normal`/`pii`→standard, `scrub`/`full`→strict.

`--entities` overrides mode preset. YAML `mode:` / `entities:` supported.

---

## Pipeline (mental model)

1. **Extract** (`extract/`): PDF (reflow + NBSP, header/footer strip), DOCX body, text. Optional OCR.
2. **Repair** (`text_repair.py`): rejoin split emails etc.
3. **Analyze once** on joined blocks (`engine.DocumentAnonymizer`):  
   spaCy NER → patterns/heuristics (custom recognizers) → optional LLM → denylist → merge → filters → **org stem expansion**.
4. **Placeholders** (`mapping.py`): stable `[PERSON_1]`, `[ORG_2]`, `[CITY_1]`, `[VIN_1]`, …
5. **Review** (optional): un-redact selected tags (`review.py`).
6. **Write** Markdown + optional `--map` JSON (contains PII; mode `0600`).

Single-pass analysis + project spans to blocks (not per-block NER). Keep it that way for performance.

---

## Design rules (do not break)

1. **No production hard-coded lists of real companies/people.**  
   Synthetic strings in tests/LLM few-shots are for teaching only.  
   Company short forms come from **document-local stems** (`org_stems.py`) after legal-form ORG hits.

2. **Offline default.** Network only via explicit `--llm` + provider.  
   `xai` must warn and respect `--offline`.  
   Only `llm.py` should perform network I/O for inference.

3. **False-positive discipline over recall of noise.**  
   Prefer missing a borderline ORG to redacting `Force Majeure`, `Asiakas`, section headers, or km-limits as postcodes.

4. **PDF chrome:** strip running headers/footers by default (`extract/headers.py`).  
   Opt-in keep: `--keep-headers`.

5. **Placeholders must stay stable** within a document (`normalize_entity_text` casefold).

6. **Do not invent exploit payloads** or commit customer documents (`/test.pdf`, `test*.pdf` gitignored).

---

## Where to change what

| Goal | Start here |
|------|------------|
| New entity type | `recognizers/`, `TYPE_LABELS` in `mapping.py`, mode lists in `config.py`, `_ENTITY_PRIORITY` / standalone list in `engine.py` |
| False positive ORG/LOCATION | `engine._filter_false_org_location`, `brand_org.py`, `org_stems.py` |
| Address / postcode / city | `recognizers/street.py`, `fi_postal.py` (NBSP gaps, no `\n\n` postcode+city) |
| FI phone / plate / hetu / VAT | `recognizers/fi_*.py` |
| PDF line breaks / emails | `extract/pdf.py` (`_join_pdf_lines`), `extract/text_repair.py` |
| Headers/footers | `extract/headers.py` |
| CLI flags / modes / review | `cli.py`, `review.py` |
| Progress UI | `util/progress.py` |

---

## Testing conventions

- **Framework:** pytest; `pythonpath = ["src"]`.
- **Fixtures:** synthetic PII only (`tests/fixtures/contract_*.txt`, realworld annexes).  
  Document public sources in `tests/fixtures/realworld/SOURCES.md`.
- **No network** in default tests (`test_offline_security.py`).
- Prefer unit tests on pure helpers (`find_*`, `repair_*`, `filter_running_headers`, `normalize_placeholder`) plus a few engine/CLI smokes.
- Interactive `--review` must not hang CI: non-TTY errors; mock `questionary` for checkbox paths.
- Run full suite before claiming done: `pytest -q` (expect ~136+ tests with models installed).

---

## CLI surface (agents should not regress)

```text
anonymize FILE                    # strict
anonymize extract|standard|strict FILE
anonymize doctor | examples
--review / --no-review / --review-window / --review-cli / --reject LIST
--keep-headers
--mode / --lang / --entities / --map / --config
--format md|source|both / --fail-on-native-miss / --native-min-match-rate
--llm / --llm-provider ollama|xai / --offline
--force-ocr / --no-ocr
-o / --out-dir / -q / -v
```

Verb rewrite lives in `cli._preprocess_argv` — preserve `run()` as entrypoint.

Default outputs:

- redact modes → `{stem}.anonymized.md`
- extract → `{stem}.md` (or `.extracted.md` if that would overwrite)

---

## Security checklist for changes

- [ ] No new network calls outside `llm.py` without explicit opt-in  
- [ ] Map files still treated as sensitive  
- [ ] No real names/IDs from private PDFs in tests or samples  
- [ ] LLM remote path still warns  
- [ ] Installer does not require sudo for core install  

---

## Style notes

- Python 3.11+, `from __future__ import annotations`, dataclasses for models.
- Line length ~100 (ruff config present).
- Prefer small pure functions + Presidio `EntityRecognizer` classes for detectors.
- User-facing stderr: Rich; progress must not corrupt `-o -` stdout Markdown.
- Commit messages: complete sentences; explain *why* for non-trivial fixes.

---

## Out of scope unless asked

- Microsoft Store / MSIX only distribution  
- Hard-coded Finnish company/insurer lists  
- Guaranteeing 100% recall/precision  
- Changing default mode away from `strict` without an explicit product decision  
- Changing Windows packaging layout without an explicit product decision

---

## Quick “done” criteria

1. `pytest -q` green with project venv + spaCy models  
2. `anonymize doctor` still meaningful  
3. No junk/PII staged; respect `.gitignore`  
4. README/CLI help still match real flags if user-facing behaviour changed  
