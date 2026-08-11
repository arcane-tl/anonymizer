# Windows GUI + CLI install

Thin desktop UI matching the **Mac Anonymizer** options panel. Detection stays in the `anonymize` CLI.

## Install (end users) — recommended

**One file:** download **`Anonymizer-Setup-<version>.exe`** from
[GitHub Releases](https://github.com/arcane-tl/anonymizer/releases).

1. Double-click the Setup wizard  
2. Finish → Start Menu **Anonymizer**  
3. Optional: “Add CLI to PATH” installs `anonymize` for terminals  

If SmartScreen warns on an **unsigned** build: *More info* → *Run anyway*  
(signed builds are the goal for public releases).

Portable (advanced): **`Anonymizer-<version>-windows.zip`** — unzip and run `Anonymizer.exe`
(needs the included `runtime\` folder next to it).

### Dev / from source (PowerShell)

Does **not** register in Windows **Apps & features**. Prefer **Setup.exe** for end users who need Add/Remove Programs.

```powershell
.\scripts\install.ps1 -Yes -FromSource
```

This installs:

| Piece | Location |
|-------|----------|
| CLI | `%LOCALAPPDATA%\Anonymizer\bin\anonymize.cmd` on user PATH |
| GUI | Start Menu **Anonymizer** (Anonymizer logo icon) + `anonymize-gui.cmd` |
| Config lists | `%USERPROFILE%\.config\anonymizer\config.yaml` |

Start Menu / desktop shortcuts use `packaging/windows/icons/Anonymizer.ico` (same logo as Mac). From-source install copies it to `%LOCALAPPDATA%\Anonymizer\Anonymizer.ico` and sets the `.lnk` icon; Setup builds embed it in `Anonymizer.exe` via PyInstaller.

Uninstall PowerShell install:

```powershell
.\scripts\uninstall.ps1 -Yes
# or:
& "$env:LOCALAPPDATA\Anonymizer\scripts\uninstall.ps1" -Yes
```

Uninstall **Setup.exe** install: **Settings → Apps → Anonymizer**, or `unins000.exe` under `%LOCALAPPDATA%\Anonymizer`.

## Use GUI

```text
Start Menu → Anonymizer
  or:  anonymize-gui
  or:  anonymize-gui path\to\a.pdf path\to\b.docx
```

Opens straight into the **options** panel (same product logic as Mac):

- No files yet → **+** under Files (add from several folders). **−** removes.
- Drag-drop / argv paths pre-fill the list.
- **Output folder** defaults to *same folder as source file (default)*; **Choose…** sets CLI `--out-dir`.
- **Templates…**, mode / style / format, Review (document window), Open when finished — same layout idea as Mac.

### GUI won’t open / no log file

`%TEMP%` is not a folder name you type in Explorer as-is for searching blindly.
In PowerShell the log path is:

```powershell
echo $env:TEMP\anonymizer-gui.log
# typical real path:
# C:\Users\YOURNAME\AppData\Local\Temp\anonymizer-gui.log
```

If the log **still doesn’t exist**, the updated launcher never ran. Diagnose:

```powershell
cd path\to\anonymizer
git pull
powershell -ExecutionPolicy Bypass -File .\packaging\windows\diagnose-gui.ps1
```

Or step by step:

```powershell
# 1) Does the command exist?
Get-Command anonymize-gui -ErrorAction SilentlyContinue
Get-Command anonymize -ErrorAction SilentlyContinue

# 2) Run the real installer GUI script (shows errors)
& "$env:LOCALAPPDATA\anonymizer\bin\anonymize-gui.cmd"

# 3) Or call Python directly
& "$env:LOCALAPPDATA\anonymizer\.venv\Scripts\python.exe" -m anonymizer.gui

# 4) Tk test (must print "tkinter OK")
& "$env:LOCALAPPDATA\anonymizer\.venv\Scripts\python.exe" -c "import tkinter; print('tkinter OK')"
```

Then reinstall from the branch:

```powershell
cd path\to\anonymizer
git checkout feature/domain-fp-filters
git pull
.\scripts\install.ps1 -Yes -FromSource
```

Use a **new** PowerShell window after install.

Options (same as Mac):

- Mode pop-up: Strict / Standard / Extract  
- Output style pop-up: stable placeholders or delete redacted data  
- Output format pop-up: Markdown / Source filetype / Both  
- **Templates…** — allow/deny packs (enable for run, edit user packs)  
- Review findings before saving (default on) — **Teach into** pack is on the review window  
- Open result when finished  

## Helper (advanced)

`run-anonymize.ps1` mirrors `packaging/macos/run-anonymize.sh` for scripted multi-file runs.

## Dev

```powershell
python -m anonymizer.gui
# or
anonymize-gui
```

## Building Setup.exe (maintainers / CI)

### One-shot release build (copy-paste)

Run on a **Windows** PC on the **same commit as the Mac release** (usually tag `v1.4.0` or `main` after the version bump):

```powershell
# 0) Clone or update (same commit as the Mac release)
git clone https://github.com/arcane-tl/anonymizer.git
cd anonymizer
# or:  cd path\to\anonymizer
git fetch --tags
git checkout v1.4.0   # or: git checkout main && git pull

# Confirm version (must match the release tag, e.g. 1.4.0)
Select-String -Path pyproject.toml -Pattern '^version\s*='
# 1) Prerequisites (once per machine)
#    - Python 3.11+ on the *build host* (for PyInstaller + wheel)
#      winget install Python.Python.3.12
#    - Inno Setup 6 (required for Setup.exe; zip still builds without it)
#      winget install --id JRSoftware.InnoSetup -e
#      https://jrsoftware.org/isinfo.php
#    Network required once: embeddable CPython 3.12 + spaCy models + pip packages.

# 2) Build stage + portable zip + Setup.exe
#    Default: EN+FI large spaCy models (best PERSON/ORG quality; larger download)
#    Host Python must be able to `import yaml` after the script installs freeze deps
#    (PyYAML is bundled into Anonymizer.exe; missing host pyyaml caused empty freeze).
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build-release.ps1
# Smaller installer (faster, less NER quality):
#   ... build-release.ps1 -Models sm

# 3) Confirm outputs
Get-ChildItem dist\Anonymizer-*-windows.zip, dist\Anonymizer-Setup-*.exe
```

Expected files (version from `pyproject.toml`):

| Artifact | Path |
|----------|------|
| Portable zip | `dist\Anonymizer-<ver>-windows.zip` |
| Setup wizard | `dist\Anonymizer-Setup-<ver>.exe` |
| Stage (for local smoke) | `dist\windows-stage\` |

**Next:** smoke-test (below), then copy **both** `Anonymizer-Setup-*.exe` and `Anonymizer-*-windows.zip` to the Mac/release machine and attach them to the GitHub Release `vX.Y.Z` alongside the Mac zip.

What the build puts under `dist\windows-stage\`:

| Piece | Role |
|-------|------|
| `Anonymizer.exe` | Frozen GUI only (PyInstaller; no spaCy) |
| `runtime\` | **Embeddable CPython 3.12** + package + spaCy **lg** EN+FI models by default (relocatable; end users need **no** system Python) |
| `bin\anonymize.cmd` | CLI: `runtime\python.exe -m anonymizer.cli` |
| `bin\Anonymizer.cmd` | Launches GUI |

Post-install: switch model size or add Swedish — see `docs/models.md`.

Install target (Setup): `%LOCALAPPDATA%\Anonymizer` (per-user, no admin). Optional task adds `bin\` to the user PATH.

### Smoke-check a local build

```powershell
# CLI (portable stage)
.\dist\windows-stage\bin\anonymize.cmd --version
.\dist\windows-stage\bin\anonymize.cmd doctor
.\dist\windows-stage\bin\anonymize.cmd --mode standard tests\fixtures\sample_en.pdf `
  -o $env:TEMP\smoke.md --format both

# GUI (needs runtime\ next to Anonymizer.exe)
Start-Process .\dist\windows-stage\Anonymizer.exe
# Log if needed:  $env:TEMP\anonymizer-gui.log

# Full Setup install (recommended before public release)
Start-Process .\dist\Anonymizer-Setup-*.exe -Wait
# Then: Start Menu → Anonymizer; Settings → Apps → Anonymizer (uninstall)
```

### GitHub Actions / Release

`.github/workflows/windows-release.yml` builds on tag `v*` or `workflow_dispatch` and uploads artifacts. You still attach Setup + zip to the GitHub Release manually (or via `gh release upload`).

### Code signing (recommended before wide release)

Unsigned builds trigger SmartScreen (“More info” → “Run anyway”). For public releases:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
  dist\Anonymizer-Setup-*.exe dist\windows-stage\Anonymizer.exe
```

Requires a code-signing certificate (not included in the repo).

### Notes

- **Host Python** may be 3.11–3.13 with **tkinter** (python.org installer); **runtime** is embeddable **3.12.x** plus **copied Tcl/Tk** from the host so `--review-window` works without a system Python on the user PC.
- Deep worktree paths: the build script may create a short junction (`C:\anon-stage`) so Inno Setup does not abort on long paths.
- `scripts\install.ps1` remains the **developer** path (user venv under `%LOCALAPPDATA%\anonymizer`).

## Parity notes

| Mac | Windows |
|-----|---------|
| AppleScript panel | tkinter (`anonymizer.gui`) |
| `run-anonymize.sh` | `run-anonymize.ps1` |
| Terminal.app for review | Windows Terminal / `cmd` |
| Homebrew cask app | Start Menu + `anonymize-gui` |
