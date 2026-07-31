# Mac GUI (droplet) — experimental

Drag PDF / DOCX / text files onto **Anonymizer** without using Terminal.

This is a thin wrapper around the `anonymize` CLI (same engine, same modes).  
Developed on branch `feature/macos-gui`; install the CLI first.

## Prerequisites

1. **macOS**
2. **anonymizer CLI** installed and working:

```bash
curl -fsSL https://raw.githubusercontent.com/arcane-tl/anonymizer/main/scripts/install.sh | bash -s -- --yes
anonymize doctor
```

Or from a clone (dev):

```bash
# with your venv active and `anonymize` on PATH
anonymize doctor
```

## Install the app

From a clone of this repo:

```bash
chmod +x packaging/macos/install-app.sh packaging/macos/run-anonymize.sh
./packaging/macos/install-app.sh
```

This builds `Anonymizer.app` with `osacompile` and installs it to **`~/Applications/Anonymizer.app`**.

Optional:

```bash
./packaging/macos/install-app.sh --dest /Applications
```

## Use — one wizard at drop time

1. Drag files onto **Anonymizer** (or double-click → file picker).
2. Answer every question **before** work starts:

| Step | What you see |
|------|----------------|
| **Files** | List of documents you dropped → Continue |
| **Goal** | Plain language: full scrub / identity only / text only |
| **Review?** | Only for scrub modes — optional checklist in Terminal |
| **Open?** | Open the Markdown when finished? (Yes/No) — chosen **now** |
| **Confirm** | Summary of all choices → **Start** |
| **Done** | What was created + **Show in Finder** / OK |

3. Markdown is written **next to each source file**  
   (`file.anonymized.md`, or `file.md` for text-only).

### Goals (map to CLI modes)

| In the app | CLI |
|------------|-----|
| Remove personal details (recommended) | `strict` |
| Remove identity only (keep company names) | `standard` |
| Convert to text only (no privacy scrub) | `extract` |

### Review in Terminal

Interactive review needs a real terminal (checkbox UI). If you choose Review:

1. You get a short explanation first.
2. **Terminal** opens for the checklist (space = keep clear, enter = save).
3. Opening the result follows the **Open?** choice you already made (no second prompt).

## How it works

| Piece | Role |
|-------|------|
| `Anonymizer.app` | Wizard + droplet |
| `run-anonymize.sh` | Finds CLI; prints `OUTPUT:` paths; honors `ANONYMIZER_OPEN` |
| `anonymize` CLI | Extraction + redaction engine |

CLI search order:

1. `$ANONYMIZER_BIN`
2. `~/.local/bin/anonymize`
3. `anonymize` on `PATH`

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Dialog: could not find anonymize | Install CLI; new terminal; `anonymize doctor` |
| App won’t open (quarantine) | Right-click → Open, or re-run `install-app.sh` |
| No output file | Writable folder next to the source |
| Dev CLI in a venv | `export ANONYMIZER_BIN="$(which anonymize)"` or symlink into `~/.local/bin` |

## Uninstall

```bash
rm -rf ~/Applications/Anonymizer.app
```

CLI uninstall is separate (`scripts/uninstall.sh` if you used the full installer).

## Developer notes

- Rebuild after editing AppleScript or the helper: re-run `install-app.sh`.
- Tests: `pytest tests/test_macos_run_anonymize.py`.
- Do not commit a built `.app`; compile on the user’s machine.
