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

## Use

1. Open **Finder → Applications** (or **~/Applications**).
2. Drag one or more `.pdf` / `.docx` / `.txt` / `.md` files onto **Anonymizer**.
3. Choose a mode:
   - **strict** — full scrub (default)
   - **standard** — people & contact; keeps companies
   - **extract** — text only, no redaction
4. **Review?** (strict / standard only) — **Yes** opens **Terminal** with  
   `anonymize … --review` (checkbox list: space = keep clear, enter = write).  
   After review, Terminal asks whether to **open** the Markdown file(s).
5. Without review: the app runs quietly, then asks **Open the anonymized file now?**  
   (**Open** / **Not now**).

Markdown is written **next to the source file**  
(`file.anonymized.md` or `file.md` for extract).

Double-click the app (no drop) → file picker.

> **Why Terminal for review?** The interactive checklist needs a real terminal  
> (`do shell script` has no TTY). Non-review runs stay fully dialog-based.

## How it works

| Piece | Role |
|-------|------|
| `Anonymizer.app` | AppleScript droplet (drag/drop + mode dialog) |
| `run-anonymize.sh` | Finds CLI, runs `anonymize <mode> <file> --quiet` |
| `anonymize` CLI | Real extraction + redaction engine |

CLI search order:

1. `$ANONYMIZER_BIN`
2. `~/.local/bin/anonymize`
3. `anonymize` on `PATH`

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Dialog: could not find anonymize | Install CLI; open a new terminal; `anonymize doctor` |
| App won’t open (quarantine) | Right-click → Open, or re-run `install-app.sh` |
| No output file | Check mode; ensure the source folder is writable |
| Dev CLI in a venv | `export ANONYMIZER_BIN="$(which anonymize)"` then re-run helper, or put a symlink in `~/.local/bin` |

## Uninstall

```bash
rm -rf ~/Applications/Anonymizer.app
# or: /Applications/Anonymizer.app
```

The CLI is separate (`scripts/uninstall.sh` if you used the full installer).

## Developer notes

- Rebuild after editing the AppleScript or shell helper: re-run `install-app.sh`.
- Automated tests for the shell helper: `pytest tests/test_macos_run_anonymize.py`.
- Do not commit a built `.app` binary; always compile on the user’s machine.
