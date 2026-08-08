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
| GUI | Start Menu **Anonymizer** + `anonymize-gui.cmd` |
| Config lists | `%USERPROFILE%\.config\anonymizer\config.yaml` |

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

First window is always **Anonymizer** with **Choose documents…** (then the options panel).

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

- Mode: strict / standard / extract  
- Output style: tags vs delete  
- Lists… (allow / deny → config YAML)  
- Review (opens terminal checklist)  
- Open result when finished  
- Also save redacted original (PDF/DOCX) → `--format both`  

## Helper (advanced)

`run-anonymize.ps1` mirrors `packaging/macos/run-anonymize.sh` for scripted multi-file runs.

## Dev

```powershell
python -m anonymizer.gui
# or
anonymize-gui
```

## Building Setup.exe (maintainers / CI)

On a **Windows** machine (or `windows-latest` CI):

```powershell
# Prerequisites:
#   - Python 3.11+ on the *build host* (for PyInstaller + wheel build)
#   - Inno Setup 6 for Setup.exe (optional; zip still builds without it)
#       winget install --id JRSoftware.InnoSetup -e
#       https://jrsoftware.org/isinfo.php
# Network required once: downloads embeddable CPython 3.12 + spaCy models.

powershell -ExecutionPolicy Bypass -File .\packaging\windows\build-release.ps1
```

What the build produces under `dist\windows-stage\`:

| Piece | Role |
|-------|------|
| `Anonymizer.exe` | Frozen GUI only (PyInstaller; no spaCy) |
| `runtime\` | **Embeddable CPython 3.12** + package + spaCy `sm` models (relocatable; end users need **no** system Python) |
| `bin\anonymize.cmd` | CLI: `runtime\python.exe -m anonymizer.cli` |
| `bin\Anonymizer.cmd` | Launches GUI |

Outputs:

| Artifact | Path |
|----------|------|
| Stage (GUI + runtime + models) | `dist\windows-stage\` |
| Portable zip | `dist\Anonymizer-<ver>-windows.zip` |
| Setup wizard | `dist\Anonymizer-Setup-<ver>.exe` (if ISCC found) |

Install target (Setup): `%LOCALAPPDATA%\Anonymizer` (per-user, no admin). Optional task adds `bin\` to the user PATH.

### Smoke-check a local build

```powershell
# CLI (portable stage)
.\dist\windows-stage\bin\anonymize.cmd doctor
.\dist\windows-stage\bin\anonymize.cmd --mode standard tests\fixtures\sample_en.pdf `
  -o $env:TEMP\smoke.md --format both

# GUI (needs runtime\ next to Anonymizer.exe)
Start-Process .\dist\windows-stage\Anonymizer.exe
# Log if needed:  $env:TEMP\anonymizer-gui.log
```

### GitHub Actions / Release

1. Copy the template into the live workflows tree (not done automatically):

   ```text
   packaging/windows/ci/windows-release.yml  →  .github/workflows/windows-release.yml
   ```

2. On tag `v*` or `workflow_dispatch`, CI builds zip + Setup and uploads artifacts.

3. Attach `Anonymizer-Setup-<ver>.exe` and `Anonymizer-<ver>-windows.zip` to the GitHub Release.

### Code signing (recommended before wide release)

Unsigned builds trigger SmartScreen (“More info” → “Run anyway”). For public releases:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
  dist\Anonymizer-Setup-*.exe dist\windows-stage\Anonymizer.exe
```

Requires a code-signing certificate (not included in the repo).

### Notes

- **Host Python** may be 3.11–3.13; **runtime** is always embeddable **3.12.x** (pinned in `build-release.ps1`).
- Deep worktree paths: the build script may create a short junction (`C:\anon-stage`) so Inno Setup does not abort on long paths.
- `scripts\install.ps1` remains the **developer** path (user venv under `%LOCALAPPDATA%\anonymizer`).

## Parity notes

| Mac | Windows |
|-----|---------|
| AppleScript panel | tkinter (`anonymizer.gui`) |
| `run-anonymize.sh` | `run-anonymize.ps1` |
| Terminal.app for review | Windows Terminal / `cmd` |
| Homebrew cask app | Start Menu + `anonymize-gui` |
