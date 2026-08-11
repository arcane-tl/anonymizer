#Requires -Version 5.1
<#
.SYNOPSIS
  Launch the Anonymizer GUI from this git worktree (dev), with a console.

.DESCRIPTION
  Sets PYTHONPATH to ./src so you test branch code, not an old install.
  Prefer this over Start-Process from an agent — keeps stderr + log visible.

.EXAMPLE
  # Options window with sample PDF
  powershell -ExecutionPolicy Bypass -File .\scripts\run-gui-dev.ps1

.EXAMPLE
  # File picker / launcher only
  powershell -ExecutionPolicy Bypass -File .\scripts\run-gui-dev.ps1 -Picker

.EXAMPLE
  # Custom file + debug MessageBoxes
  powershell -ExecutionPolicy Bypass -File .\scripts\run-gui-dev.ps1 -File .\samples\en\x.pdf -DebugGui

.EXAMPLE
  # Tk smoke test only (tiny window)
  powershell -ExecutionPolicy Bypass -File .\scripts\run-gui-dev.ps1 -TkOnly
#>
param(
    [string]$File = "",
    [switch]$Picker,
    [switch]$DebugGui,
    [switch]$TkOnly,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "src\anonymizer"))) {
    # scripts/ is under repo root
    $Root = $PSScriptRoot
    if (-not (Test-Path (Join-Path $Root "src\anonymizer"))) {
        $Root = Split-Path -Parent $PSScriptRoot
    }
}
Set-Location $Root

$src = Join-Path $Root "src"
$log = Join-Path $env:TEMP "anonymizer-gui.log"
$env:PYTHONPATH = $src

function Find-Python {
    param([string]$Preferred)
    if ($Preferred -and (Test-Path $Preferred)) { return $Preferred }
    $candidates = @(
        (Join-Path $env:USERPROFILE "Downloads\anonymizer\.venv\Scripts\python.exe"),
        (Join-Path $Root ".venv\Scripts\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Anonymizer\runtime\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Anonymizer\.venv\Scripts\python.exe")
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "No python.exe found. Pass -Python path\to\python.exe"
}

$py = Find-Python -Preferred $Python

Write-Host "=== Anonymizer GUI (dev) ===" -ForegroundColor Cyan
Write-Host "Root     = $Root"
Write-Host "Python   = $py"
Write-Host "PYTHONPATH = $env:PYTHONPATH"
Write-Host "Log      = $log"
Write-Host ""

& $py -c "import sys; print('exe', sys.executable); print('ver', sys.version)"
& $py -c "import anonymizer; print('anonymizer', anonymizer.__version__, anonymizer.__file__)"
if ($LASTEXITCODE -ne 0) { throw "Failed to import anonymizer from $src" }

if ($TkOnly) {
    Write-Host "Tk smoke: close the small window to finish." -ForegroundColor Yellow
    & $py -c "import tkinter as tk; r=tk.Tk(); r.title('Tk OK'); r.geometry('260x100+200+200'); r.mainloop(); print('tk closed ok')"
    exit $LASTEXITCODE
}

if ($DebugGui) {
    $env:ANONYMIZER_GUI_DEBUG = "1"
    Write-Host "ANONYMIZER_GUI_DEBUG=1 (step MessageBoxes on)" -ForegroundColor Yellow
}

$argv = @("-m", "anonymizer.gui")
if (-not $Picker) {
    if (-not $File) {
        $sample = Join-Path $Root "samples\en\loc_purchase_agreement.pdf"
        if (Test-Path $sample) { $File = $sample }
    }
    if ($File) {
        if (-not (Test-Path $File)) { throw "File not found: $File" }
        $argv += (Resolve-Path $File).Path
        Write-Host "Mode     = Options with file" -ForegroundColor Green
        Write-Host "File     = $($argv[-1])"
    } else {
        Write-Host "Mode     = Launcher (no sample file found)" -ForegroundColor Yellow
    }
} else {
    Write-Host "Mode     = Launcher / file picker" -ForegroundColor Green
}

Write-Host ""
Write-Host "Starting GUI (close the window to return here)…" -ForegroundColor Cyan
Write-Host "Command: $py $($argv -join ' ')"
Write-Host ""

& $py @argv
$code = $LASTEXITCODE
Write-Host ""
Write-Host "Exit code: $code" -ForegroundColor $(if ($code -eq 0) { "Green" } else { "Red" })
if (Test-Path $log) {
    Write-Host "--- log tail ---" -ForegroundColor Cyan
    Get-Content $log -Tail 40
}
exit $code
