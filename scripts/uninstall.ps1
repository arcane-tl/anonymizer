#Requires -Version 5.1
<#
.SYNOPSIS
  Remove an anonymizer install created by install.ps1 on Windows.

.PARAMETER Prefix
  Install root (default: %LOCALAPPDATA%\anonymizer)

.PARAMETER BinDir
  Launcher directory (default: %LOCALAPPDATA%\anonymizer\bin)

.PARAMETER KeepFiles
  Only remove the launcher; leave the install prefix on disk

.PARAMETER Yes
  Non-interactive
#>
[CmdletBinding()]
param(
    [string] $Prefix = $(if ($env:ANONYMIZER_PREFIX) { $env:ANONYMIZER_PREFIX } else { Join-Path $env:LOCALAPPDATA "anonymizer" }),
    [string] $BinDir = $(if ($env:ANONYMIZER_BIN_DIR) { $env:ANONYMIZER_BIN_DIR } else { Join-Path $env:LOCALAPPDATA "anonymizer\bin" }),
    [switch] $KeepFiles,
    [switch] $Yes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Ok([string] $Message)   { Write-Host "OK  $Message" -ForegroundColor Green }
function Write-Warn([string] $Message) { Write-Host "!   $Message" -ForegroundColor Yellow }
function Write-Info([string] $Message) { Write-Host "==> $Message" -ForegroundColor Cyan }

function Confirm-Step([string] $Prompt) {
    if ($Yes) { return $true }
    $ans = Read-Host "$Prompt [y/N]"
    return ($ans -eq "y" -or $ans -eq "Y" -or $ans -eq "yes")
}

foreach ($name in @("anonymize.cmd", "anonymize-gui.cmd")) {
    $launcher = Join-Path $BinDir $name
    if (Test-Path $launcher) {
        $text = Get-Content -Raw $launcher -ErrorAction SilentlyContinue
        if ($text -and ($text -like "*$Prefix*" -or $text -like "*.venv\Scripts\*")) {
            if (Confirm-Step "Remove launcher $launcher?") {
                Remove-Item -Force $launcher
                Write-Ok "Removed $launcher"
            }
        } else {
            Write-Warn "Launcher $launcher does not look like this install — leaving it alone"
        }
    }
}

$startMenuLnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Anonymizer.lnk"
if (Test-Path -LiteralPath $startMenuLnk) {
    if (Confirm-Step "Remove Start Menu shortcut $startMenuLnk?") {
        Remove-Item -Force $startMenuLnk
        Write-Ok "Removed Start Menu shortcut"
    }
}

$scriptDir = $PSScriptRoot
$repoRoot = Split-Path -Parent $scriptDir
$isRepo = (Test-Path (Join-Path $repoRoot "pyproject.toml"))

if ($isRepo -and ((Resolve-Path $Prefix -ErrorAction SilentlyContinue).Path -eq (Resolve-Path $repoRoot -ErrorAction SilentlyContinue).Path)) {
    $venv = Join-Path $repoRoot ".venv"
    if (Test-Path $venv) {
        if (Confirm-Step "Remove virtualenv $venv?") {
            Remove-Item -Recurse -Force $venv
            Write-Ok "Removed $venv"
        }
    }
} elseif ((Test-Path $Prefix) -and -not $KeepFiles) {
    if (Confirm-Step "Remove install directory $Prefix?") {
        Remove-Item -Recurse -Force $Prefix
        Write-Ok "Removed $Prefix"
    }
}

# Optionally strip BinDir from user PATH if empty and we added it
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -and (Test-Path $BinDir) -eq $false) {
    $parts = $userPath -split ";" | Where-Object { $_ -ne "" -and $_ -ne $BinDir }
    # only remove if directory gone
}

Write-Ok "Uninstall finished"
Write-Host "Note: system Python and Tesseract (if installed) were left alone."
