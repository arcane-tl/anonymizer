# Mac GUI (droplet)

Drag PDF / DOCX / text files onto **Anonymizer** without using Terminal.

Thin wrapper around the `anonymize` CLI.

## Prerequisites

1. **macOS**
2. Working CLI (`anonymize` on PATH) — Homebrew preferred:

```bash
brew tap arcane-tl/anonymizer
brew trust arcane-tl/anonymizer
brew install --cask anonymizer-app   # app + CLI
# or CLI only: brew install anonymizer
anonymize doctor
```

For **Windows** install (Setup.exe / Apps & features), see [../windows/README.md](../windows/README.md).

## Install the app (end users)

Prefer the **cask** (signed + notarized release):

```bash
brew install --cask anonymizer-app
# → /Applications/Anonymizer.app
```

### Local dev install (from clone)

```bash
chmod +x packaging/macos/install-app.sh packaging/macos/run-anonymize.sh
./packaging/macos/install-app.sh
# → ~/Applications/Anonymizer.app  (ad-hoc signed for local use)
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

Icons are **bundle `.icns` only** (full-bleed square). macOS applies the
rounded squircle. Do **not** use `fileicon set` on the app — that draws a
sharp custom square and breaks size/shape next to other apps.

## Use — one options window

1. **Double-click** the app → options opens with **no files** (add with **+**).  
   **Drop** files onto Anonymizer → options opens with those files pre-filled.
2. A **single window** shows:
   - **Files** — list with **+** (Add file) / **−** (Remove file); multi-location add  
   - **Mode** pop-up — Strict / Standard / Extract  
   - **Output style** pop-up — stable placeholders or delete redacted data  
   - **Output format** pop-up — Markdown / Source filetype / Both  
   - **Output folder** — default *same folder as source file (default)*, or **Choose…** a directory (`--out-dir`)  
   - **Templates…** — native AppKit pack editor; enable packs for this run  
   - ☑ **Review findings before saving** (default on) — teach packs from the **review window**  
   - ☑ **Open result when finished**  
   - Action bar: **Templates…** left · **Cancel** + **Start** right  

**Templates…** is a native panel in the droplet (not Tk). Data goes through `templates-io.sh` → `python -m anonymizer.templates_io`.  
Selection is stored as `templates_enabled` in `~/.config/anonymizer/config.yaml`.  
Windows Tk options/templates share the same product logic.  
**Teach** keep-clear / new adds into a user pack from the review window (not the options panel).
3. Click **Start** (or Cancel). Start requires at least one file.
4. When finished (no review path):
   - **Open** checked → file opens; no extra Finder/OK popup (notification only)
   - **Open** unchecked → one **Done** dialog with **Show in Finder**

```text
Open app or drop files → [ Options window ] → work → [ Done ]
```

### Modes (pop-up)

| Label | CLI |
|-------|-----|
| Strict - Remove all sensitive data (recommended) | `strict` |
| Standard - Remove sensitive personal data | `standard` |
| Extract - Keep all the data | `extract` |

### Review

Needs a real terminal for the checkbox UI. If Review is checked, Terminal opens after Start; opening the result follows the Open checkbox (no second prompt).

## How it works

| Piece | Role |
|-------|------|
| `Anonymizer.app` | ASObjC options panel + droplet |
| `run-anonymize.sh` | CLI discovery, `OUTPUT:` paths, `ANONYMIZER_OPEN` |
| `anonymize` | Engine |

## Release (Developer ID + notarization)

Shipping to other Macs via Homebrew cask requires **Developer ID Application**
signing and Apple **notarization**. Use the local release script:

```bash
# One-time: certificate in Keychain
security find-identity -v -p codesigning
# expect: Developer ID Application: Your Name (TEAMID)

# One-time: App Store Connect API key → notarytool profile
xcrun notarytool store-credentials anonymizer-notary \
  --key ~/path/to/AuthKey_XXXXXXXXXX.p8 \
  --key-id XXXXXXXXXX \
  --issuer XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX

# Build → sign → notarize → staple → dist/Anonymizer-VERSION.zip
./packaging/macos/release-app.sh --version 1.0.1
```

| File | Role |
|------|------|
| `install-app.sh` | Compile droplet + icons + plist; ad-hoc sign for **dev** |
| `release-app.sh` | Production: Developer ID, hardened runtime, notary, staple, zip |
| `Anonymizer.entitlements` | Hardened Runtime entitlements (Apple Events) |

Never commit `.p8` keys, certs, or `dist/*.zip` secrets. `dist/` is gitignored.

After release:

1. Upload `dist/Anonymizer-VERSION.zip` to the GitHub Release  
2. Update `sha256` / `version` in `packaging/homebrew/Casks/anonymizer-app.rb`  
3. Sync the public tap (`packaging/homebrew/README.md`)

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| can’t find anonymize | Install CLI; `anonymize doctor` |
| **“Anonymizer is damaged…”** | `brew reinstall --cask anonymizer-app`. Interim: `xattr -cr /Applications/Anonymizer.app` then right-click → Open |
| quarantine / unidentified developer | Prefer notarized cask; or right-click → Open |
| Options window empty / crash | Rebuild with `./packaging/macos/install-app.sh` |
| release-app: 0 identities | Install Developer ID Application cert (see Release section) |
| notarytool profile missing | `store-credentials anonymizer-notary` with your API key |

## Uninstall

```bash
brew uninstall --cask anonymizer
# or local:
rm -rf ~/Applications/Anonymizer.app /Applications/Anonymizer.app
```

## Developer notes

- Rebuild after AppleScript changes: `./packaging/macos/install-app.sh`
- Helper tests: `pytest tests/test_macos_run_anonymize.py`
- Do not commit the built `.app`
- Always re-codesign **after** Info.plist / icon edits (install-app does this; release-app reseals with Developer ID)
