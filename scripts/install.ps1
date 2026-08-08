#Requires -Version 5.1
<#
.SYNOPSIS
  Install anonymizer CLI on Windows (local, offline-by-default runtime).

.DESCRIPTION
  Creates a Python venv under the install prefix, installs the package and
  spaCy models (EN + FI), and places an "anonymize.cmd" launcher on the
  user PATH.

.PARAMETER Prefix
  Install root (default: %LOCALAPPDATA%\anonymizer)

.PARAMETER BinDir
  Directory for anonymize.cmd (default: %LOCALAPPDATA%\anonymizer\bin)

.PARAMETER FromSource
  Install from the current git clone (editable) instead of cloning GitHub

.PARAMETER Repo
  Git clone URL (default: https://github.com/arcane-tl/anonymizer.git)

.PARAMETER Branch
  Git branch to clone (default: main)

.PARAMETER Models
  spaCy model size: sm (default, faster) or lg (higher accuracy)

.PARAMETER WithDev
  Also install pytest (dev extra)

.PARAMETER Python
  Path to a Python 3.11+ executable (optional)

.PARAMETER Yes
  Non-interactive (required for unattended / CI)

.EXAMPLE
  # From an elevated or normal PowerShell:
  irm https://raw.githubusercontent.com/arcane-tl/anonymizer/main/scripts/install.ps1 -OutFile install.ps1
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -Yes

.EXAMPLE
  # From a clone:
  .\scripts\install.ps1 -Yes -FromSource
#>
[CmdletBinding()]
param(
    [string] $Prefix = $(if ($env:ANONYMIZER_PREFIX) { $env:ANONYMIZER_PREFIX } else { Join-Path $env:LOCALAPPDATA "anonymizer" }),
    [string] $BinDir = $(if ($env:ANONYMIZER_BIN_DIR) { $env:ANONYMIZER_BIN_DIR } else { Join-Path $env:LOCALAPPDATA "anonymizer\bin" }),
    [switch] $FromSource,
    [string] $Repo = $(if ($env:ANONYMIZER_REPO) { $env:ANONYMIZER_REPO } else { "https://github.com/arcane-tl/anonymizer.git" }),
    [string] $Branch = $(if ($env:ANONYMIZER_BRANCH) { $env:ANONYMIZER_BRANCH } else { "main" }),
    [ValidateSet("sm", "lg")]
    [string] $Models = "sm",
    [switch] $WithDev,
    [string] $Python = "",
    [switch] $Yes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info([string] $Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok([string] $Message)   { Write-Host "OK  $Message" -ForegroundColor Green }
function Write-Warn([string] $Message) { Write-Host "!   $Message" -ForegroundColor Yellow }
function Die([string] $Message) {
    Write-Host "error: $Message" -ForegroundColor Red
    exit 1
}

function Confirm-Step([string] $Prompt) {
    if ($Yes) { return $true }
    $ans = Read-Host "$Prompt [y/N]"
    return ($ans -eq "y" -or $ans -eq "Y" -or $ans -eq "yes")
}

function Test-PythonVersion([string] $Exe) {
    try {
        $out = & $Exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if (-not $out) { return $false }
        $parts = $out.Trim().Split(".")
        $major = [int]$parts[0]
        $minor = [int]$parts[1]
        return ($major -gt 3) -or ($major -eq 3 -and $minor -ge 11)
    } catch {
        return $false
    }
}

function Find-Python {
    if ($Python) {
        if (Test-PythonVersion $Python) { return $Python }
        Die "Python at -Python path is missing or older than 3.11: $Python"
    }
    $candidates = @()
    # py launcher
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in @("-3.13", "-3.12", "-3.11", "-3")) {
            try {
                $p = & py $v -c "import sys; print(sys.executable)" 2>$null
                if ($p -and (Test-PythonVersion $p.Trim())) {
                    return $p.Trim()
                }
            } catch { }
        }
    }
    foreach ($name in @("python3.13", "python3.12", "python3.11", "python3", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and (Test-PythonVersion $cmd.Source)) {
            return $cmd.Source
        }
    }
    return $null
}

function Ensure-Source {
    $script:InstallRoot = $null
    $script:Editable = $true

    $here = $PSScriptRoot
    $repoCandidate = Split-Path -Parent $here
    $fromSourceTree = $false
    if ((Test-Path (Join-Path $repoCandidate "pyproject.toml")) -and
        (Select-String -Path (Join-Path $repoCandidate "pyproject.toml") -Pattern 'name = "anonymizer"' -Quiet)) {
        $fromSourceTree = $true
    }

    if ($FromSource) {
        if (-not $fromSourceTree) {
            Die "-FromSource requires running scripts\install.ps1 from a cloned anonymizer repo"
        }
        $script:InstallRoot = $repoCandidate
        Write-Ok "Using source tree: $($script:InstallRoot)"
        return
    }

    # Clone or update into Prefix
    $script:InstallRoot = $Prefix
    if (Test-Path (Join-Path $Prefix ".git")) {
        Write-Info "Updating existing install at $Prefix ..."
        Push-Location $Prefix
        try {
            git fetch --quiet origin $Branch 2>$null
            git checkout --quiet $Branch 2>$null
            git pull --ff-only --quiet origin $Branch 2>$null
            if ($LASTEXITCODE -ne 0) { Write-Warn "git pull failed; using existing tree" }
        } finally {
            Pop-Location
        }
    } elseif ((Test-Path (Join-Path $Prefix "pyproject.toml"))) {
        Write-Ok "Using existing tree at $Prefix"
    } else {
        if ($fromSourceTree -and -not $FromSource) {
            # Prefer cloning still for "installed" layout, unless user asked FromSource
        }
        if (Test-Path $Prefix) {
            $items = @(Get-ChildItem -Force $Prefix -ErrorAction SilentlyContinue)
            if ($items.Count -gt 0) {
                Die "Prefix $Prefix exists and is not a git checkout. Remove it or pick another -Prefix."
            }
        }
        Write-Info "Cloning $Repo (branch $Branch) → $Prefix"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Prefix) | Out-Null
        git clone --depth 1 --branch $Branch $Repo $Prefix
        if ($LASTEXITCODE -ne 0) { Die "git clone failed" }
    }
    Write-Ok "Install root: $($script:InstallRoot)"
}

function Setup-PythonEnv {
    $venv = Join-Path $script:InstallRoot ".venv"
    Write-Info "Creating virtualenv at $venv"
    & $script:PyExe -m venv $venv
    if ($LASTEXITCODE -ne 0) { Die "python -m venv failed" }

    $pip = Join-Path $venv "Scripts\pip.exe"
    $pyVenv = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path $pyVenv)) { Die "venv python not found at $pyVenv" }

    Write-Info "Upgrading pip..."
    & $pyVenv -m pip install --upgrade pip setuptools wheel | Out-Null

    Write-Info "Installing anonymizer package..."
    Push-Location $script:InstallRoot
    try {
        if ($WithDev) {
            & $pyVenv -m pip install -e ".[dev]"
        } else {
            & $pyVenv -m pip install -e .
        }
        if ($LASTEXITCODE -ne 0) { Die "pip install failed" }
    } finally {
        Pop-Location
    }

    if ($Models -eq "lg") {
        $enModel = "en_core_web_lg"
        $fiModel = "fi_core_news_lg"
    } else {
        $enModel = "en_core_web_sm"
        $fiModel = "fi_core_news_sm"
    }

    Write-Info "Downloading spaCy models ($Models)..."
    & $pyVenv -m spacy download $enModel
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Failed $enModel — trying en_core_web_sm"
        & $pyVenv -m spacy download en_core_web_sm
        if ($LASTEXITCODE -ne 0) { Die "Could not install English spaCy model" }
    }
    & $pyVenv -m spacy download $fiModel
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Failed $fiModel — trying fi_core_news_sm"
        & $pyVenv -m spacy download fi_core_news_sm
        if ($LASTEXITCODE -ne 0) { Die "Could not install Finnish spaCy model" }
    }
    Write-Ok "Python package and models installed"
}

function Install-Launcher {
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    $venvAnonymize = Join-Path $script:InstallRoot ".venv\Scripts\anonymize.exe"
    if (-not (Test-Path $venvAnonymize)) {
        # entry-point might be anonymize without .exe in some layouts
        $alt = Join-Path $script:InstallRoot ".venv\Scripts\anonymize"
        if (Test-Path $alt) { $venvAnonymize = $alt }
        else { Die "Expected CLI at $venvAnonymize not found" }
    }

    $launcher = Join-Path $BinDir "anonymize.cmd"
    # Quote the exe path for spaces under %LOCALAPPDATA%
    $content = @(
        "@echo off"
        "REM Generated by anonymizer install.ps1 — do not edit."
        "`"$venvAnonymize`" %*"
        "exit /b %ERRORLEVEL%"
    ) -join "`r`n"
    Set-Content -Path $launcher -Value $content -Encoding ASCII
    Write-Ok "CLI installed: $launcher"

    # User PATH
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) { $userPath = "" }
    $parts = $userPath -split ";" | Where-Object { $_ -ne "" }
    if ($parts -contains $BinDir) {
        Write-Ok "$BinDir is already on the user PATH"
    } else {
        if ($Yes -or (Confirm-Step "Add $BinDir to your user PATH?")) {
            $newPath = if ($userPath.TrimEnd(";")) { "$userPath;$BinDir" } else { $BinDir }
            [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
            $env:Path = "$env:Path;$BinDir"
            Write-Ok "Added $BinDir to user PATH (new terminals pick this up)"
        } else {
            Write-Warn "Add manually to PATH: $BinDir"
        }
    }
}

function Test-Install {
    Write-Info "Verifying install..."
    $cli = Join-Path $BinDir "anonymize.cmd"
    & $cli --version
    if ($LASTEXITCODE -ne 0) { Die "anonymize --version failed" }
    & $cli doctor
    Write-Ok "anonymize is ready"
}

function Write-Summary {
    Write-Host ""
    Write-Host "Installation complete" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Install root:  $($script:InstallRoot)"
    Write-Host "  CLI:           $(Join-Path $BinDir 'anonymize.cmd')"
    Write-Host "  Config sample: $(Join-Path $script:InstallRoot 'config.example.yaml')"
    Write-Host ""
    Write-Host "Try it (new PowerShell window recommended):" -ForegroundColor Cyan
    Write-Host "  anonymize doctor"
    Write-Host "  anonymize extract path\to\document.pdf"
    Write-Host "  anonymize path\to\document.pdf"
    Write-Host "  anonymize standard path\to\contract.pdf"
    Write-Host ""
    Write-Host "  anonymize examples"
    Write-Host "  anonymize --help"
    Write-Host ""
    Write-Host "Upgrade later:"
    Write-Host "  & `"$($script:InstallRoot)\scripts\install.ps1`" -Yes -FromSource"
    Write-Host "  # or re-run the download installer"
    Write-Host ""
    Write-Host "Uninstall:"
    Write-Host "  & `"$($script:InstallRoot)\scripts\uninstall.ps1`" -Yes"
    Write-Host ""
    Write-Host "GUI (options window, Mac-parity):"
    Write-Host "  anonymize-gui"
    Write-Host "  # or Start Menu → Anonymizer (if shortcut was created)"
    Write-Host ""
    Write-Host "OCR (optional, scanned PDFs): install Tesseract for Windows and ensure it is on PATH."
    Write-Host "  https://github.com/UB-Mannheim/tesseract/wiki"
    Write-Host ""
}

function Install-GuiShortcut {
    # Start Menu + optional desktop shortcut → pythonw -m anonymizer.gui
    $venvPythonw = Join-Path $script:InstallRoot ".venv\Scripts\pythonw.exe"
    $venvPython = Join-Path $script:InstallRoot ".venv\Scripts\python.exe"
    $pyw = if (Test-Path -LiteralPath $venvPythonw) { $venvPythonw } else { $venvPython }
    if (-not (Test-Path -LiteralPath $pyw)) {
        Write-Warn "GUI launcher skipped (venv python not found)"
        return
    }
    $programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    New-Item -ItemType Directory -Force -Path $programs | Out-Null
    $lnkPath = Join-Path $programs "Anonymizer.lnk"
    try {
        $w = New-Object -ComObject WScript.Shell
        $sc = $w.CreateShortcut($lnkPath)
        $sc.TargetPath = $pyw
        $sc.Arguments = "-m anonymizer.gui"
        $sc.WorkingDirectory = $script:InstallRoot
        $sc.WindowStyle = 1
        $sc.Description = "Anonymizer — drag-and-drop document redaction"
        $sc.Save()
        Write-Ok "Start Menu shortcut: $lnkPath"
    } catch {
        Write-Warn "Could not create Start Menu shortcut: $_"
    }
    # also anonymize-gui.cmd next to anonymize.cmd
    $guiCmd = Join-Path $BinDir "anonymize-gui.cmd"
    $guiBat = @"
@echo off
REM Generated by anonymizer install.ps1
"$pyw" -m anonymizer.gui %*
"@
    Set-Content -Path $guiCmd -Value $guiBat -Encoding ASCII
    Write-Ok "GUI launcher: $guiCmd"
}

# ---------------------------------------------------------------------------
Write-Info "anonymizer Windows installer"
Write-Info "OS: $([System.Environment]::OSVersion.VersionString)"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Die "git is required. Install Git for Windows: https://git-scm.com/download/win"
}

$script:PyExe = Find-Python
if (-not $script:PyExe) {
    Die "Python 3.11+ is required. Install from https://www.python.org/downloads/ (check 'Add python.exe to PATH') or use the 'py' launcher."
}
$ver = & $script:PyExe -c "import sys; print(sys.version.split()[0])"
Write-Ok "Python: $($script:PyExe) ($ver)"

Ensure-Source
Setup-PythonEnv
Install-Launcher
Install-GuiShortcut
Test-Install
Write-Summary
