#Requires -Version 5.1
<#
.SYNOPSIS
  Remove an anonymizer install created by install.ps1 on Windows.

.PARAMETER Prefix
  Install root (default: %LOCALAPPDATA%\Anonymizer)

.PARAMETER BinDir
  Launcher directory (default: %LOCALAPPDATA%\Anonymizer\bin)

.PARAMETER KeepFiles
  Only remove launchers/shortcuts; leave the install prefix on disk

.PARAMETER Yes
  Non-interactive (assume yes for all removals)

.EXAMPLE
  .\scripts\uninstall.ps1 -Yes

.EXAMPLE
  # Old lowercase install root:
  .\scripts\uninstall.ps1 -Yes -Prefix "$env:LOCALAPPDATA\anonymizer" -BinDir "$env:LOCALAPPDATA\anonymizer\bin"
#>
[CmdletBinding()]
param(
    [string] $Prefix = $(if ($env:ANONYMIZER_PREFIX) { $env:ANONYMIZER_PREFIX } else { Join-Path $env:LOCALAPPDATA "Anonymizer" }),
    [string] $BinDir = $(if ($env:ANONYMIZER_BIN_DIR) { $env:ANONYMIZER_BIN_DIR } else { Join-Path $env:LOCALAPPDATA "Anonymizer\bin" }),
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

function Remove-Launcher([string] $LauncherPath, [string] $InstallPrefix) {
    if (-not (Test-Path -LiteralPath $LauncherPath)) {
        return
    }
    $text = ""
    try {
        $text = Get-Content -LiteralPath $LauncherPath -Raw -ErrorAction SilentlyContinue
        if ($null -eq $text) { $text = "" }
    } catch {
        $text = ""
    }
    $looksOurs = ($text -like "*$InstallPrefix*") -or
                 ($text -like "*.venv\Scripts\*") -or
                 ($text -like "*\runtime\Scripts\*") -or
                 ($text -like "*anonymizer*")
    if (-not $looksOurs) {
        Write-Warn "Launcher ${LauncherPath} does not look like this install — leaving it alone"
        return
    }
    # Use ${var} so "?" is not part of the variable name under StrictMode
    if (Confirm-Step "Remove launcher ${LauncherPath}?") {
        Remove-Item -LiteralPath $LauncherPath -Force
        Write-Ok "Removed ${LauncherPath}"
    }
}

Write-Info "Uninstalling anonymizer (Prefix=$Prefix)"

# Launchers under default + legacy BinDir
$binDirs = @(
    $BinDir,
    (Join-Path $env:LOCALAPPDATA "Anonymizer\bin"),
    (Join-Path $env:LOCALAPPDATA "anonymizer\bin")
) | Select-Object -Unique

foreach ($dir in $binDirs) {
    if (-not $dir) { continue }
    foreach ($name in @("anonymize.cmd", "anonymize-gui.cmd", "Anonymizer.cmd")) {
        $launcherPath = Join-Path $dir $name
        Remove-Launcher -LauncherPath $launcherPath -InstallPrefix $Prefix
    }
}

$startMenuLnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Anonymizer.lnk"
if (Test-Path -LiteralPath $startMenuLnk) {
    if (Confirm-Step "Remove Start Menu shortcut ${startMenuLnk}?") {
        Remove-Item -LiteralPath $startMenuLnk -Force
        Write-Ok "Removed Start Menu shortcut"
    }
}

# Install trees: current + legacy lowercase
$prefixes = @(
    $Prefix,
    (Join-Path $env:LOCALAPPDATA "Anonymizer"),
    (Join-Path $env:LOCALAPPDATA "anonymizer")
) | Select-Object -Unique

$scriptDir = $PSScriptRoot
$repoRoot = Split-Path -Parent $scriptDir
$isRepo = Test-Path (Join-Path $repoRoot "pyproject.toml")

foreach ($p in $prefixes) {
    if (-not $p) { continue }
    if (-not (Test-Path -LiteralPath $p)) { continue }

    $resolvedPrefix = $null
    $resolvedRepo = $null
    try { $resolvedPrefix = (Resolve-Path -LiteralPath $p).Path } catch { }
    try { $resolvedRepo = (Resolve-Path -LiteralPath $repoRoot).Path } catch { }

    if ($isRepo -and $resolvedPrefix -and $resolvedRepo -and ($resolvedPrefix -eq $resolvedRepo)) {
        $venv = Join-Path $repoRoot ".venv"
        if (Test-Path -LiteralPath $venv) {
            if (Confirm-Step "Remove virtualenv ${venv}?") {
                Remove-Item -LiteralPath $venv -Recurse -Force
                Write-Ok "Removed ${venv}"
            }
        }
        continue
    }

    if (-not $KeepFiles) {
        if (Confirm-Step "Remove install directory ${p}?") {
            Remove-Item -LiteralPath $p -Recurse -Force
            Write-Ok "Removed ${p}"
        }
    }
}

# Strip BinDir entries from user PATH when those dirs are gone
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $parts = $userPath -split ";" | Where-Object {
        $_ -and
        $_ -ne "" -and
        -not ($_ -match '[\\/]Anonymizer[\\/]bin$') -and
        -not ($_ -match '[\\/]anonymizer[\\/]bin$')
    }
    # Only rewrite PATH if something was removed AND user confirmed full uninstall
    $newPath = ($parts -join ";").TrimEnd(";")
    if ($newPath -ne $userPath.TrimEnd(";")) {
        if (Confirm-Step "Remove Anonymizer bin folders from user PATH (y/N)?") {
            [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
            Write-Ok "Updated user PATH"
        }
    }
}

Write-Ok "Uninstall finished"
Write-Host "Note: system Python, Tesseract, and your git clone (if any) were left alone."
Write-Host "Open a new PowerShell window so PATH changes apply."
