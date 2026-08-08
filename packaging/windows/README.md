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

### GUI won’t open / flashes and closes

1. Run in a **visible** console (not only the Start Menu):
   ```powershell
   anonymize-gui
   ```
2. Check the log: `%TEMP%\anonymizer-gui.log`
3. Test Tk:
   ```powershell
   & "$env:LOCALAPPDATA\anonymizer\.venv\Scripts\python.exe" -c "import tkinter; tkinter.Tk().title('ok'); input('press enter')"
   ```
   If that fails, reinstall **Python from python.org** with Tcl/Tk, then:
   ```powershell
   .\scripts\install.ps1 -Yes -FromSource
   ```
4. Re-create launchers after pulling fixes (same install command).

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
