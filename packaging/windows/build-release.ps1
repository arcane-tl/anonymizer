#Requires -Version 5.1
<#
.SYNOPSIS
  Build Windows release layout + optional Inno Setup installer.

.DESCRIPTION
  Creates dist/windows-stage/ with:
    Anonymizer.exe   (frozen GUI via PyInstaller)
    runtime/         (venv: anonymizer + spaCy sm models)
    bin/anonymize.cmd
    bin/Anonymizer.cmd

  If ISCC (Inno Setup) is on PATH, also builds:
    dist/Anonymizer-Setup-<version>.exe

.EXAMPLE
  # On a Windows machine / CI (Python 3.11+ required for the build host):
  powershell -ExecutionPolicy Bypass -File .\packaging\windows\build-release.ps1

.NOTES
  End users should run Anonymizer-Setup-*.exe, not this script.
#>
[CmdletBinding()]
param(
    [string] $Python = "",
    [ValidateSet("sm", "lg")]
    [string] $Models = "sm",
    [switch] $SkipInstaller,
    [switch] $SkipGuiFreeze
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info([string] $m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok([string] $m)   { Write-Host "OK  $m" -ForegroundColor Green }
function Die([string] $m) { Write-Host "error: $m" -ForegroundColor Red; exit 1 }

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

# Version from pyproject.toml
$verLine = Select-String -Path (Join-Path $Root "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $verLine) { Die "version not found in pyproject.toml" }
$Version = $verLine.Matches[0].Groups[1].Value
Write-Info "Version $Version"

function Find-Python {
    if ($Python) { return $Python }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in @("-3.12", "-3.11", "-3.13", "-3")) {
            try {
                $p = & py $v -c "import sys; print(sys.executable)" 2>$null
                if ($p) { return $p.Trim() }
            } catch {}
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return (Get-Command python).Source
    }
    Die "Python 3.11+ required on the build machine"
}

$Py = Find-Python
Write-Ok "Build Python: $Py"

$Stage = Join-Path $Root "dist\windows-stage"
$Dist = Join-Path $Root "dist"
New-Item -ItemType Directory -Force -Path $Dist | Out-Null
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "bin") | Out-Null

# --- runtime venv with package + models ---
$Runtime = Join-Path $Stage "runtime"
Write-Info "Creating runtime venv at $Runtime"
& $Py -m venv $Runtime
$Pip = Join-Path $Runtime "Scripts\pip.exe"
$PyV = Join-Path $Runtime "Scripts\python.exe"
& $PyV -m pip install --upgrade pip setuptools wheel | Out-Null

Write-Info "Installing anonymizer into runtime..."
& $Pip install "$Root"
if ($LASTEXITCODE -ne 0) { Die "pip install failed" }

if ($Models -eq "lg") {
    $en = "en_core_web_lg"; $fi = "fi_core_news_lg"
} else {
    $en = "en_core_web_sm"; $fi = "fi_core_news_sm"
}
Write-Info "Downloading spaCy models ($Models)..."
& $PyV -m spacy download $en
if ($LASTEXITCODE -ne 0) { Die "spacy download $en failed" }
& $PyV -m spacy download $fi
if ($LASTEXITCODE -ne 0) { Die "spacy download $fi failed" }

# CLI launcher
$anonExe = Join-Path $Runtime "Scripts\anonymize.exe"
if (-not (Test-Path $anonExe)) { Die "anonymize.exe missing after install" }
$cmd = @"
@echo off
REM Anonymizer CLI — installed by Setup / build-release.ps1
"%~dp0..\runtime\Scripts\anonymize.exe" %*
exit /b %ERRORLEVEL%
"@
Set-Content -Path (Join-Path $Stage "bin\anonymize.cmd") -Value $cmd -Encoding ASCII
Write-Ok "bin\anonymize.cmd"

# --- freeze GUI ---
if (-not $SkipGuiFreeze) {
    Write-Info "Installing PyInstaller into build env..."
    & $Py -m pip install -q "pyinstaller>=6.0"
    Write-Info "Freezing Anonymizer.exe (GUI only)..."
    $spec = Join-Path $Root "packaging\windows\Anonymizer.spec"
    & $Py -m PyInstaller --noconfirm --clean --distpath (Join-Path $Stage "app") --workpath (Join-Path $Dist "pyi-work") $spec
    if ($LASTEXITCODE -ne 0) { Die "PyInstaller failed" }
    $guiExe = Join-Path $Stage "app\Anonymizer.exe"
    if (-not (Test-Path $guiExe)) {
        # onefile may land directly under app/
        $alt = Get-ChildItem -Path (Join-Path $Stage "app") -Filter "Anonymizer.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($alt) { $guiExe = $alt.FullName }
    }
    if (-not (Test-Path $guiExe)) { Die "Anonymizer.exe not produced" }
    # Promote to stage root for simple shortcuts
    Copy-Item -Force $guiExe (Join-Path $Stage "Anonymizer.exe")
    Write-Ok "Anonymizer.exe"

    $guiCmd = @"
@echo off
start `"`" "%~dp0..\Anonymizer.exe" %*
"@
    Set-Content -Path (Join-Path $Stage "bin\Anonymizer.cmd") -Value $guiCmd -Encoding ASCII
} else {
    Write-Info "SkipGuiFreeze: writing pythonw launcher instead"
    $guiCmd = @"
@echo off
"%~dp0..\runtime\Scripts\pythonw.exe" -m anonymizer.gui %*
"@
    Set-Content -Path (Join-Path $Stage "bin\Anonymizer.cmd") -Value $guiCmd -Encoding ASCII
    Copy-Item (Join-Path $Stage "bin\Anonymizer.cmd") (Join-Path $Stage "Anonymizer.cmd")
}

# Version stamp
Set-Content -Path (Join-Path $Stage "VERSION") -Value $Version -Encoding ASCII -NoNewline

# Zip portable stage
$zip = Join-Path $Dist "Anonymizer-$Version-windows.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Write-Info "Zipping $zip"
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $zip -Force
Write-Ok $zip

# --- Inno Setup ---
if ($SkipInstaller) {
    Write-Info "SkipInstaller set — stage + zip only"
    exit 0
}

$iscc = $null
foreach ($c in @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    (Get-Command iscc -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
)) {
    if ($c -and (Test-Path $c)) { $iscc = $c; break }
}
if (-not $iscc) {
    Write-Host "!   Inno Setup (ISCC.exe) not found — install from https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
    Write-Host "    Stage is ready at $Stage; zip at $zip" -ForegroundColor Yellow
    exit 0
}

$iss = Join-Path $Root "packaging\windows\installer\anonymizer.iss"
Write-Info "Compiling installer with $iscc"
& $iscc /DMyAppVersion=$Version /DMyStageDir="$Stage" $iss
if ($LASTEXITCODE -ne 0) { Die "ISCC failed" }
$setup = Join-Path $Dist "Anonymizer-Setup-$Version.exe"
if (Test-Path $setup) {
    Write-Ok "Installer: $setup"
} else {
    # Inno may write next to iss OutputDir
    $found = Get-ChildItem -Path $Dist -Filter "Anonymizer-Setup*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { Write-Ok "Installer: $($found.FullName)" }
    else { Write-Host "!   Setup exe not found in dist\ — check Inno OutputDir" -ForegroundColor Yellow }
}

Write-Ok "Windows release build finished"
