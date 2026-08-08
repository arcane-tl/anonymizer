# Windows GUI + CLI install

Thin desktop UI matching the **Mac Anonymizer** options panel. Detection stays in the `anonymize` CLI.

## Install (end users)

```powershell
irm https://raw.githubusercontent.com/arcane-tl/anonymizer/main/scripts/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Yes
```

Or from a clone:

```powershell
.\scripts\install.ps1 -Yes -FromSource
```

This installs:

| Piece | Location |
|-------|----------|
| CLI | `%LOCALAPPDATA%\anonymizer` + `anonymize.cmd` on user PATH |
| GUI | Start Menu **Anonymizer** + `anonymize-gui.cmd` |
| Config lists | `%USERPROFILE%\.config\anonymizer\config.yaml` |

Uninstall:

```powershell
& "$env:LOCALAPPDATA\anonymizer\scripts\uninstall.ps1" -Yes
```

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

Optional frozen `.exe` (later): PyInstaller on `anonymizer.gui:main` — not required for first Windows GUI.

## Parity notes

| Mac | Windows |
|-----|---------|
| AppleScript panel | tkinter (`anonymizer.gui`) |
| `run-anonymize.sh` | `run-anonymize.ps1` |
| Terminal.app for review | Windows Terminal / `cmd` |
| Homebrew cask app | Start Menu + `anonymize-gui` |
