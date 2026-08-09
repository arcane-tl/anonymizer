# Custom recognizers and extra languages

Anonymizer ships **English + Finnish** by default (spaCy NER, validated FI IDs, domain FP filters). You can add **domain-specific IDs** and **extra languages** without forking the package.

## YAML pattern recognizers (recommended)

Create a small YAML file:

```yaml
name: EmployeeIdPatterns
entity_type: EMPLOYEE_ID
label: EMP_ID          # placeholder stem → [EMP_ID_1]
priority: 3            # merge priority (IDs ≈ 3, PERSON/ORG ≈ 2)
modes: [strict, standard]
patterns:
  - name: emp_badge
    regex: '\bEMP-\d{6}\b'
    score: 0.9
```

Point config at it (paths are relative to the config file):

```yaml
# config.yaml
recognizers:
  - path: ./patterns/employee_id.yaml
```

```bash
anonymize report.pdf --config config.yaml
```

See `examples/plugins/employee_id.yaml` for a complete sample.

**Rules**

- Local files only (no URL download).
- Prefer simple `\b…\b` patterns (avoid catastrophic backtracking).
- Types are registered into the entity registry so modes, placeholders, and merge priority stay consistent.
- Do not put real customer IDs into the repo or tests.

## Python recognizers (advanced)

For checksums or multi-span logic, implement a Presidio `EntityRecognizer` (same shape as `FiHetuRecognizer`):

```yaml
recognizers:
  - module: mypackage.ids:EmployeeIdRecognizer
  # or load a single file:
  - python: ./plugins/employee_id.py
    class: EmployeeIdRecognizer
    label: EMP_ID
    priority: 3
```

The class must subclass `presidio_analyzer.EntityRecognizer` and set `supported_entities`.

## Extra languages and model sizes

Installers default to **EN + FI large** models. Swedish and other sizes are opt-in.

**Full guide:** [models.md](models.md) (switch sm/md/lg, add Swedish, Homebrew/Windows paths).

```bash
# Optional Swedish
python -m spacy download sv_core_news_lg
anonymize doc.pdf --lang sv
anonymize doc.pdf --lang en,sv
```

`anonymize doctor` treats **en** and **fi** as required; **sv** as optional.

```yaml
# config.yaml — force a package if several sizes are installed
spacy_models:
  en: en_core_web_md
  sv: sv_core_news_lg
```

Auto-detect (`--lang auto`) uses Lingua over EN/FI/SV and may run multi-pass NER when mixed.

## Entity types and modes

Built-in mode presets (`strict` / `standard` / `extract`) are defined in `config.py`. Custom types declare `modes: [strict, standard]` in YAML so they join those presets when you do **not** pass an explicit `entities:` list.

Explicit entity lists still win:

```yaml
entities:
  - PERSON
  - EMAIL_ADDRESS
  - EMPLOYEE_ID
```

## Security

- Plugins load only when listed in config.
- No automatic scanning of `site-packages`.
- Offline default unchanged (no network for plugins).
