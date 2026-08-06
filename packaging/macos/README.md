# Mac GUI (droplet) — experimental

Drag PDF / DOCX / text files onto **Anonymizer** without using Terminal.

Thin wrapper around the `anonymize` CLI. Branch: `feature/macos-gui`.

## Prerequisites

1. **macOS**
2. Working CLI (`anonymize` on PATH) — Homebrew preferred:

```bash
brew install --HEAD --formula ./packaging/homebrew/anonymizer.rb
# or: curl installer — see root README / scripts/install.sh
anonymize doctor
```

## Install the app

```bash
chmod +x packaging/macos/install-app.sh packaging/macos/run-anonymize.sh
./packaging/macos/install-app.sh
# → ~/Applications/Anonymizer.app
```

### App icon

Custom icon assets live in `packaging/macos/icons/`:

| File | Use |
|------|-----|
| `Anonymizer.icns` | Installed app icon (applied by `install-app.sh`) |
| `Anonymizer-transparent.png` | Master **RGBA** (transparent background) |
| `Anonymizer-1024.png` | 1024 master PNG with alpha |
| `source-user-choice.png` | Original selected artwork |
| `icon-small-optimized.jpg` | Small-size optimized source before alpha |

Theme: document + magnifying glass + lock on a **full-bleed dark plate**.

**Important:** masters are **opaque 1024×1024 squares** (no pre-rounded transparent
corners). macOS applies the continuous squircle mask itself—pre-rounding caused a
double-frame look next to App Store / Calculator / Chess.

If Finder still shows the default AppleScript “document arrow” icon after install:

```bash
brew install fileicon   # once
./packaging/macos/install-app.sh
# then: open ~/Applications, or log out/in if the Dock caches the old icon
```

## Use — one options window

1. Drop files onto **Anonymizer** (or double-click → pick files).
2. A **single window** shows:
   - File list  
   - **Mode** as a visible radio list (all three choices at once — not a menu)  
   - ☑ **Review findings before saving** (Terminal checklist; off for text-only)  
   - ☑ **Open result when finished**  
3. Click **Start** (or Cancel).
4. When finished (no review path):
   - **Open** checked → file opens; no extra Finder/OK popup (notification only)
   - **Open** unchecked → one **Done** dialog with **Show in Finder**

```text
Drop → [ Options window ] → work → [ Done ]
```

### Modes (in-window list)

| Label | CLI |
|-------|-----|
| Remove personal details (recommended) | `strict` |
| Remove identity only (keep company names) | `standard` |
| Convert to text only (no privacy scrub) | `extract` |

### Review

Needs a real terminal for the checkbox UI. If Review is checked, Terminal opens after Start; opening the result follows the Open checkbox (no second prompt).

## How it works

| Piece | Role |
|-------|------|
| `Anonymizer.app` | ASObjC options panel + droplet |
| `run-anonymize.sh` | CLI discovery, `OUTPUT:` paths, `ANONYMIZER_OPEN` |
| `anonymize` | Engine |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| can’t find anonymize | Install CLI; `anonymize doctor` |
| quarantine | Right-click → Open; re-run `install-app.sh` |
| Options window empty / crash | Rebuild with `./packaging/macos/install-app.sh` |

## Uninstall

```bash
rm -rf ~/Applications/Anonymizer.app
```

## Developer notes

- Rebuild after AppleScript changes: `./packaging/macos/install-app.sh`
- Helper tests: `pytest tests/test_macos_run_anonymize.py`
- Do not commit the built `.app`
