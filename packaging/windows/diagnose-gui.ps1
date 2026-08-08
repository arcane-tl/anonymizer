#Requires -Version 5.1
<#
.SYNOPSIS
  Diagnose why anonymize-gui does not open on Windows.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\packaging\windows\diagnose-gui.ps1
#>
$ErrorActionPreference = "Continue"

function Section([string]$Title) {
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
}

$log = Join-Path $env:TEMP "anonymizer-gui.log"
# Prefer Setup layout (Anonymizer); fall back to legacy lowercase install.ps1 path
$prefix = $null
foreach ($name in @("Anonymizer", "anonymizer")) {
    $cand = Join-Path $env:LOCALAPPDATA $name
    if (Test-Path $cand) { $prefix = $cand; break }
}
if (-not $prefix) { $prefix = Join-Path $env:LOCALAPPDATA "Anonymizer" }
$venvPy = Join-Path $prefix ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    $venvPy = Join-Path $prefix "runtime\Scripts\python.exe"
}
$guiCmd = Join-Path $prefix "bin\anonymize-gui.cmd"
if (-not (Test-Path $guiCmd)) {
    $guiCmd = Join-Path $prefix "Anonymizer.exe"
}
$anonCmd = Join-Path $prefix "bin\anonymize.cmd"

Section "Environment"
Write-Host "USERPROFILE = $env:USERPROFILE"
Write-Host "TEMP        = $env:TEMP"
Write-Host "LOCALAPPDATA= $env:LOCALAPPDATA"
Write-Host "PATH (first 5):"
($env:PATH -split ';' | Select-Object -First 5) | ForEach-Object { Write-Host "  $_" }

Section "Launchers"
Write-Host "anonymize.cmd exists?     $(Test-Path $anonCmd)  $anonCmd"
Write-Host "anonymize-gui.cmd exists? $(Test-Path $guiCmd)  $guiCmd"
Write-Host "venv python exists?       $(Test-Path $venvPy)  $venvPy"
$which = Get-Command anonymize-gui -ErrorAction SilentlyContinue
Write-Host "Get-Command anonymize-gui: $($which.Source)"
$which2 = Get-Command anonymize -ErrorAction SilentlyContinue
Write-Host "Get-Command anonymize:     $($which2.Source)"

Section "Python + packages (venv)"
if (Test-Path $venvPy) {
    & $venvPy -c "import sys; print(sys.executable); print(sys.version)"
    & $venvPy -c "import tkinter; print('tkinter OK')" 2>&1
    & $venvPy -c "import anonymizer; print('anonymizer', anonymizer.__version__)" 2>&1
    & $venvPy -c "import anonymizer.gui; print('anonymizer.gui OK')" 2>&1
} else {
    Write-Host "No venv python at $venvPy — re-run scripts\install.ps1 -Yes -FromSource" -ForegroundColor Yellow
}

Section "Log file"
Write-Host "Expected log: $log"
if (Test-Path $log) {
    Write-Host "--- log contents ---" -ForegroundColor Green
    Get-Content $log
} else {
    Write-Host "Log does not exist yet (launcher never wrote it)." -ForegroundColor Yellow
}

Section "Try launching GUI once (10s)"
if (Test-Path $guiCmd) {
    Write-Host "Running: $guiCmd"
    $p = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$guiCmd`"" -PassThru -Wait
    Write-Host "Exit code: $($p.ExitCode)"
} elseif (Test-Path $venvPy) {
    Write-Host "Running: $venvPy -m anonymizer.gui"
    & $venvPy -m anonymizer.gui
    Write-Host "Exit code: $LASTEXITCODE"
} else {
    Write-Host "Nothing to launch."
}

Section "Log after launch"
if (Test-Path $log) {
    Write-Host "--- log contents ---" -ForegroundColor Green
    Get-Content $log
    Write-Host ""
    Write-Host "Full path to copy:" -ForegroundColor Cyan
    Write-Host (Resolve-Path $log).Path
} else {
    Write-Host "Still no log. Copy everything above and send it for debugging." -ForegroundColor Red
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
