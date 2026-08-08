<h1 align="center">
  <img src="packaging/macos/icons/Anonymizer-readme.png" alt="" width="56" height="56" align="absmiddle" />
  Anonymizer
</h1>

Turn contracts, reports, and scans into shareable Markdown — on your machine, offline by default.

**Anonymizer** is a local tool for **macOS** and **Windows**: **PDF / DOCX / plain text → Markdown**, with optional PII redaction for **English** and **Finnish**. Personal names, emails, phones, IDs, and more become stable placeholders like `[PERSON_1]` — so you can collaborate, archive, or hand a document to a model without leaking the original identifiers.

- **CLI:** `anonymize`
- **Mac app:** **Anonymizer.app** (drag-and-drop)
- **Default:** Offline — Everything stays on your computer unless you choose to use an API for local or cloud processing

> **Not a legal guarantee.** Detection is probabilistic. Always spot-check high-stakes output.

---

## Why Anonymizer

- **Privacy first** — processing is local; nothing is sent over the network unless you explicitly enable a remote LLM  
- **Real office formats** — PDF (including OCR for scans), Word (`.docx`), and text/Markdown  
- **Modes that match the job** — full scrub, identity-only, or plain text extract  
- **Stable placeholders** — the same person stays `[PERSON_1]` throughout a document  
- **English + Finnish** — auto language detection, patterns + neural NER  
- **Human in the loop** — optional review to keep false positives in clear text  
- **No hard-coded company catalogs** — patterns, models, and *your* allow/deny lists only  

---

## Before → after

Synthetic example only:

**Before**

```text
Service Agreement between Nordic Widgets Oy and Acme Logistics Ltd.
Contact: Maija Korhonen <maija.korhonen@nordic-widgets.example.fi>, +358 50 987 6543.
```

**After** (`anonymize` · strict mode)

```text
Service Agreement between [ORG_1] and [ORG_2].
Contact: [PERSON_1] <[EMAIL_1]>, [PHONE_1].
```

Same entity → same tag within that run. Export an optional map file if you need the reverse lookup later (treat it like the original document — it contains PII).

---

## Install

### macOS — Homebrew (recommended)

One product: **Anonymizer**. Terminal: **`anonymize`**. Finder: **Anonymizer.app**.

```bash
brew tap arcane-tl/anonymizer
brew trust arcane-tl/anonymizer    # Homebrew 6+ — once per machine
brew install --cask anonymizer-app # Anonymizer.app + CLI (recommended)
# CLI only: brew install anonymizer

anonymize doctor
anonymize --version
```

**Upgrade** (formula `anonymizer` + cask `anonymizer-app`):

```bash
brew update && brew upgrade anonymizer anonymizer-app
```

If you previously installed the old cask token `anonymizer` (same name as the formula), remove it so the CLI can link:

```bash
brew uninstall --cask --force anonymizer
# if that still errors:
rm -rf "$(brew --prefix)/Caskroom/anonymizer"
rm -rf /Applications/Anonymizer.app

brew install --cask anonymizer-app
brew link --overwrite anonymizer && hash -r
```

More detail: [packaging/homebrew/README.md](packaging/homebrew/README.md).

### Other options

| Platform | How |
|----------|-----|
| **macOS** (no Homebrew) | `curl -fsSL https://raw.githubusercontent.com/arcane-tl/anonymizer/main/scripts/install.sh \| bash -s -- --yes` |
| **Windows** | `scripts/install.ps1` — CLI + Start Menu GUI (`anonymize-gui`). Same options as Mac. |
| **From source** | Python 3.11+, `pip install -e ".[dev]"`, then `python -m spacy download en_core_web_lg` and `fi_core_news_lg` |

---

## 60-second tour

```bash
# Health check (models, PATH, optional OCR)
anonymize doctor

# Full scrub (default) → contract.anonymized.md
anonymize contract.pdf

# Identity only — keep company names, scrub people & contact details
anonymize standard sopimus.pdf

# Text only — no redaction
anonymize extract report.pdf

# Review redactions before writing (false positives → keep clear)
anonymize contract.pdf --review
# ↑/↓ move · space check · enter confirm
# Or non-interactive: anonymize contract.pdf --reject ORG_1,PHONE_2

# Delete findings instead of [PERSON_1] tags
anonymize contract.pdf --redact-style remove

# Also keep layout: redacted PDF/DOCX next to Markdown
anonymize contract.pdf --format both
# Native only (no Markdown): --format source

anonymize examples    # more copy-paste commands
anonymize --help
```

**Drag-and-drop (Mac):** open **Anonymizer** from Applications, drop a PDF/DOCX/txt, pick a mode. Needs the CLI on your PATH (`brew install anonymizer`).

---

## Modes

| Mode | Command | What it does | Default output |
|------|---------|--------------|----------------|
| **strict** | `anonymize FILE` | Full scrub — people, companies, addresses, geo, URLs, plates, IDs, … | `FILE.anonymized.md` |
| **standard** | `anonymize standard FILE` | Identity PII — person, email, phone, hetu, addresses, IBAN, cards, IP. **Keeps** companies, Y-tunnus, VAT, URLs, plates | `FILE.anonymized.md` |
| **extract** | `anonymize extract FILE` | Markdown only — **no redaction** | `FILE.md` |

Aliases: `text` → extract · `normal` / `pii` → standard · `scrub` / `full` → strict.

---

## Privacy & security

| Mode | Document text leaves this machine? |
|------|-------------------------------------|
| Default (`anonymize file.pdf`) | **No** — local extract, spaCy, patterns only |
| `--llm` / `--llm-provider ollama` | **No**, if Ollama is on localhost |
| `--llm --llm-provider xai` | **Yes** — sent to `https://api.x.ai` (`XAI_API_KEY`) |
| `--offline` | Blocks remote `xai` even if config enables it |

- **No telemetry** in this application  
- **`--map`** writes placeholder → original JSON (**contains PII**; mode `0600` when possible)  
- Install-time network only: `pip` / Homebrew / spaCy model download  

---

## What gets redacted (strict)

| Kind | Placeholder |
|------|-------------|
| Person | `[PERSON_n]` |
| Organization / brand | `[ORG_n]` |
| Email / phone | `[EMAIL_n]` / `[PHONE_n]` |
| Street, city, FI postcode | `[STREET_n]` / `[CITY_n]` / `[POSTAL_n]` |
| URL | `[URL_n]` |
| FI plate / hetu / Y-tunnus / VAT | `[PLATE_FI_n]` / `[FI_HETU_n]` / … |
| IBAN, card, IP, VIN (strict) | `[IBAN_n]`, … |

Dates are off by default (`--include-dates` to enable).  
`--entities …` overrides the mode preset. YAML config: [config.example.yaml](config.example.yaml).

### How detection works (short)

Patterns (IDs, emails, legal-form companies) + heuristics + **spaCy NER** (EN/FI) + domain false-positive filters (contract roles, legal collocations, form labels) + optional **LLM** proposals + **your** allow/deny lists. The app does **not** ship a list of real-world companies or people. Use `allowlist_extra` in YAML to append terms without wiping built-in label defaults.

---

## Useful options

```bash
anonymize report.pdf -o clean.md          # explicit output
anonymize ./inbox/ --out-dir ./out/       # batch folder
anonymize scan.pdf --force-ocr            # scanned PDF
anonymize doc.pdf --lang fi               # force Finnish NLP
anonymize doc.pdf --map report.map.json   # sensitive reverse map
anonymize doc.pdf --config config.yaml    # allowlist / denylist
anonymize doc.pdf --llm --llm-provider ollama   # optional local LLM layer
```

| Flag | Role |
|------|------|
| `-r` / `--review` | Checkbox: mark false positives to keep clear before write |
| `--reject LIST` | Same without a prompt (`ORG_1,PHONE_2`) |
| `--redact-style` | `placeholder` (default tags) or `remove` (delete text). Review works with both. |
| `--format` | `md` (default), `source` (redacted PDF/DOCX), or `both`. PDF = black boxes; DOCX = tags/delete. Best-effort on OCR / soft wraps. |
| `--keep-headers` | Keep PDF running headers/footers (default: strip) |
| `-o -` | Markdown on stdout (progress stays on stderr) |
| `--config` | YAML: mode, allowlist, denylist, `redact_style`, `format`, … |

**Mac app:** options include output style (tags vs delete) and **Also save redacted original (PDF/DOCX)**. **Lists…** opens allowlist/denylist in a separate window; **Done** saves to `~/.config/anonymizer/config.yaml`.

---

## Troubleshooting

| Message | Fix |
|---------|-----|
| No Cask with this name | `brew tap arcane-tl/anonymizer` |
| Untrusted tap (Homebrew 6+) | `brew trust arcane-tl/anonymizer` (note the final **r**) |
| “Anonymizer is damaged…” | `brew reinstall --cask anonymizer-app` |
| `anonymize: command not found` / `skipping link` | Uninstall old cask token: `brew uninstall --cask anonymizer`; then `brew install --cask anonymizer-app`; `brew link --overwrite anonymizer && hash -r` |

---

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download en_core_web_lg
python -m spacy download fi_core_news_lg
pytest -q
```

Regression: `tests/test_contract_templates.py`, `tests/test_realworld_precision.py`, `tests/test_offline_security.py`.  
See [tests/fixtures/README.md](tests/fixtures/README.md).

Mac GUI build: [packaging/macos/README.md](packaging/macos/README.md).

---

## Support this project

If Anonymizer is useful to you, you can support its development via GitHub Sponsors:

**[Sponsor @arcane-tl on GitHub](https://github.com/sponsors/arcane-tl)**

---

## License

MIT — see [LICENSE](LICENSE).
