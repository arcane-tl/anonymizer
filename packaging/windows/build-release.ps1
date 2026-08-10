#Requires -Version 5.1
<#
.SYNOPSIS
  Build Windows release layout + optional Inno Setup installer.

.DESCRIPTION
  Creates dist/windows-stage/ with:
    Anonymizer.exe   (frozen GUI via PyInstaller)
    runtime/         (embeddable CPython + anonymizer + spaCy models; default lg)
    bin/anonymize.cmd
    bin/Anonymizer.cmd

  runtime/ uses the official Windows embeddable package (not a venv) so the
  install is relocatable and does not require system Python on the user PC.

  If ISCC (Inno Setup) is found, also builds:
    dist/Anonymizer-Setup-<version>.exe

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\packaging\windows\build-release.ps1

.NOTES
  End users should run Anonymizer-Setup-*.exe, not this script.
#>
[CmdletBinding()]
param(
    [string] $Python = "",
    [ValidateSet("sm", "md", "lg")]
    [string] $Models = "lg",
    [string] $EmbedPythonVersion = "3.12.10",
    # Optional SHA256 of python-*-embed-amd64.zip (verify at https://www.python.org/downloads/)
    [string] $EmbedPythonSha256 = "",
    [switch] $SkipInstaller,
    [switch] $SkipGuiFreeze
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info([string] $m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok([string] $m)   { Write-Host "OK  $m" -ForegroundColor Green }
function Write-Warn([string] $m) { Write-Host "!   $m" -ForegroundColor Yellow }
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
        $src = (Get-Command python).Source
        # Ignore Windows Store alias stubs
        if ($src -notmatch "WindowsApps") { return $src }
    }
    Die "Python 3.11+ required on the build machine (host for PyInstaller)"
}

$Py = Find-Python
Write-Ok "Build host Python: $Py"

$Stage = Join-Path $Root "dist\windows-stage"
$Dist = Join-Path $Root "dist"
$Cache = Join-Path $Dist "cache"
New-Item -ItemType Directory -Force -Path $Dist | Out-Null
New-Item -ItemType Directory -Force -Path $Cache | Out-Null
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "bin") | Out-Null

# --- embeddable CPython runtime (relocatable; no system Python on user PC) ---
$Runtime = Join-Path $Stage "runtime"
$EmbedTag = $EmbedPythonVersion
$EmbedZipName = "python-$EmbedTag-embed-amd64.zip"
$EmbedUrl = "https://www.python.org/ftp/python/$EmbedTag/$EmbedZipName"
$EmbedZip = Join-Path $Cache $EmbedZipName
$GetPip = Join-Path $Cache "get-pip.py"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"

function Get-WebFile([string] $Url, [string] $OutFile, [string] $ExpectedSha256 = "") {
    if (Test-Path $OutFile) {
        $len = (Get-Item $OutFile).Length
        if ($len -gt 10000) {
            if ($ExpectedSha256) {
                $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $OutFile).Hash.ToLowerInvariant()
                if ($hash -ne $ExpectedSha256.ToLowerInvariant()) {
                    Write-Info "Cache hash mismatch for $(Split-Path $OutFile -Leaf); re-downloading"
                    Remove-Item -Force $OutFile
                } else {
                    Write-Info "Using cached $(Split-Path $OutFile -Leaf) (sha256 ok)"
                    return
                }
            } else {
                Write-Info "Using cached $(Split-Path $OutFile -Leaf) ($len bytes)"
                return
            }
        } else {
            Remove-Item -Force $OutFile
        }
    }
    Write-Info "Downloading $Url"
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        & curl.exe -fsSL -o $OutFile $Url
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $OutFile)) {
            Die "download failed: $Url"
        }
    } else {
        Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
    }
    if ($ExpectedSha256) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $OutFile).Hash.ToLowerInvariant()
        if ($hash -ne $ExpectedSha256.ToLowerInvariant()) {
            Remove-Item -Force $OutFile -ErrorAction SilentlyContinue
            Die "SHA256 mismatch for $OutFile`n  expected $ExpectedSha256`n  got      $hash"
        }
        Write-Ok "SHA256 verified for $(Split-Path $OutFile -Leaf)"
    }
}

Write-Info "Preparing embeddable CPython $EmbedTag runtime at $Runtime"
Get-WebFile $EmbedUrl $EmbedZip $EmbedPythonSha256
# get-pip.py hash changes frequently; TLS + official host only (no pin)
Get-WebFile $GetPipUrl $GetPip

New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
Expand-Archive -Path $EmbedZip -DestinationPath $Runtime -Force

$PyEmbed = Join-Path $Runtime "python.exe"
if (-not (Test-Path $PyEmbed)) { Die "embeddable python.exe missing after extract" }

# Enable site-packages (._pth ships with import site commented out)
$pthFiles = Get-ChildItem -Path $Runtime -Filter "python*._pth" -ErrorAction SilentlyContinue
if (-not $pthFiles) { Die "python*._pth not found in embeddable package" }
foreach ($pth in $pthFiles) {
    $lines = Get-Content -LiteralPath $pth.FullName
    $out = New-Object System.Collections.Generic.List[string]
    $hasSitePackages = $false
    $hasImportSite = $false
    foreach ($line in $lines) {
        $t = $line.Trim()
        if ($t -eq "Lib\\site-packages" -or $t -eq "Lib/site-packages") {
            $hasSitePackages = $true
            $out.Add("Lib\\site-packages")
            continue
        }
        if ($t -match '^#\s*import\s+site\s*$' -or $t -eq "import site") {
            $hasImportSite = $true
            $out.Add("import site")
            continue
        }
        $out.Add($line)
    }
    if (-not $hasSitePackages) {
        # Insert before import site if present, else append
        $idx = $out.IndexOf("import site")
        if ($idx -ge 0) { $out.Insert($idx, "Lib\\site-packages") }
        else { $out.Add("Lib\\site-packages") }
    }
    if (-not $hasImportSite) { $out.Add("import site") }
    # Lib + DLLs so copied tkinter / _tkinter.pyd resolve
    foreach ($extra in @("Lib", "DLLs")) {
        if (-not ($out | Where-Object { $_.Trim() -eq $extra })) {
            $idx = $out.IndexOf("import site")
            if ($idx -ge 0) { $out.Insert($idx, $extra) }
            else { $out.Add($extra) }
        }
    }
    # Write UTF-8 without BOM
    [System.IO.File]::WriteAllLines($pth.FullName, $out)
    Write-Ok "Patched $($pth.Name) for site-packages + Lib/DLLs"
}

function Copy-TkinterIntoRuntime {
    param(
        [Parameter(Mandatory = $true)][string] $HostPython,
        [Parameter(Mandatory = $true)][string] $RuntimeDir
    )
    # Embeddable CPython has no Tcl/Tk; review-window needs them on the CLI runtime.
    # Windows Python 3.8+ only loads extension DLL deps from the pyd directory,
    # the exe directory, and paths registered via os.add_dll_directory - not PATH alone.
    Write-Info "Copying tkinter/Tcl/Tk from build host into runtime..."
    $probe = "import tkinter, sys; print(sys.base_prefix)"
    $probeOut = & $HostPython -c $probe 2>&1
    if ($LASTEXITCODE -ne 0) {
        Die "Build host Python cannot import tkinter. Install python.org Python with Tcl/Tk, then rebuild.`n$probeOut"
    }
    $hostPrefix = ("$probeOut").Trim()
    if (-not $hostPrefix -or -not (Test-Path -LiteralPath $hostPrefix)) {
        Die "Could not resolve host base_prefix for tkinter copy (got: $probeOut)"
    }
    Write-Ok "Host Python prefix (tkinter): $hostPrefix"

    $dstLib = Join-Path $RuntimeDir "Lib"
    $dstDll = Join-Path $RuntimeDir "DLLs"
    $dstTcl = Join-Path $RuntimeDir "tcl"
    $dstSite = Join-Path $dstLib "site-packages"
    New-Item -ItemType Directory -Force -Path $dstLib, $dstDll, $dstSite | Out-Null

    $srcTk = Join-Path $hostPrefix "Lib\tkinter"
    if (-not (Test-Path -LiteralPath $srcTk)) {
        Die "Host missing Lib\tkinter at $srcTk"
    }
    $dstTk = Join-Path $dstLib "tkinter"
    if (Test-Path -LiteralPath $dstTk) { Remove-Item -Recurse -Force -LiteralPath $dstTk }
    Copy-Item -Recurse -Force -LiteralPath $srcTk -Destination $dstTk
    Write-Ok "Copied Lib\tkinter"

    # _tkinter.pyd + Tcl/Tk (+ common deps). Copy into DLLs\ AND next to python.exe.
    $srcDllDir = Join-Path $hostPrefix "DLLs"
    $copiedPyd = $false
    $copiedNames = New-Object System.Collections.Generic.List[string]
    $dllPatterns = @(
        "_tkinter*",
        "tcl*.dll", "tk*.dll",
        "tcl*.pyd", "tk*.pyd",
        "zlib1.dll"
    )
    $searchDirs = @()
    if (Test-Path -LiteralPath $srcDllDir) { $searchDirs += $srcDllDir }
    $searchDirs += $hostPrefix
    foreach ($dir in $searchDirs) {
        foreach ($pat in $dllPatterns) {
            Get-ChildItem -LiteralPath $dir -File -Filter $pat -ErrorAction SilentlyContinue |
                ForEach-Object {
                    Copy-Item -Force -LiteralPath $_.FullName -Destination (Join-Path $dstDll $_.Name)
                    Copy-Item -Force -LiteralPath $_.FullName -Destination (Join-Path $RuntimeDir $_.Name)
                    if (-not $copiedNames.Contains($_.Name)) { $copiedNames.Add($_.Name) }
                    if ($_.Name -like "_tkinter*") { $copiedPyd = $true }
                }
        }
    }
    if (-not $copiedPyd) {
        Die "Could not find _tkinter*.pyd under $hostPrefix (DLLs or prefix root)"
    }
    $hasTclDll = $false
    $hasTkDll = $false
    foreach ($n in $copiedNames) {
        if ($n -match '^tcl\d' -or $n -like 'tcl*.dll') { $hasTclDll = $true }
        if ($n -match '^tk\d' -or $n -like 'tk*.dll') { $hasTkDll = $true }
    }
    if (-not $hasTclDll -or -not $hasTkDll) {
        Write-Warn "Expected tcl*.dll and tk*.dll next to _tkinter; found: $($copiedNames -join ', ')"
        if (Test-Path -LiteralPath $srcDllDir) {
            Write-Warn "Host DLLs directory listing:"
            Get-ChildItem -LiteralPath $srcDllDir -File | ForEach-Object { Write-Host "  host DLL: $($_.Name)" }
        }
        Die "Missing tcl*.dll / tk*.dll from host Python DLLs - cannot load _tkinter in runtime"
    }
    Write-Ok ("Copied binaries ({0}): {1}" -f $copiedNames.Count, ($copiedNames -join ", "))

    # Tcl/Tk script library tree (tcl8.6, tk8.6, ...)
    $srcTcl = Join-Path $hostPrefix "tcl"
    if (-not (Test-Path -LiteralPath $srcTcl)) {
        Die "Host missing tcl\ directory at $srcTcl (required for tkinter scripts)"
    }
    if (Test-Path -LiteralPath $dstTcl) { Remove-Item -Recurse -Force -LiteralPath $dstTcl }
    Copy-Item -Recurse -Force -LiteralPath $srcTcl -Destination $dstTcl
    Write-Ok "Copied tcl\ library tree"

    $tclLib = Get-ChildItem -LiteralPath $dstTcl -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^tcl\d' } |
        Select-Object -First 1
    $tkLib = Get-ChildItem -LiteralPath $dstTcl -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^tk\d' } |
        Select-Object -First 1
    if (-not $tclLib -or -not $tkLib) {
        Die "tcl\ tree missing tclN.N / tkN.N folders under $dstTcl"
    }

    # sitecustomize: register DLL dirs (Win 3.8+) + TCL/TK library paths on every start
    $siteCustom = @"
# Generated by build-release.ps1 - enable tkinter in embeddable runtime.
from __future__ import annotations

import os
import sys
from pathlib import Path

def _anonymizer_tk_bootstrap() -> None:
    root = Path(sys.executable).resolve().parent
    dll = root / "DLLs"
    for d in (dll, root):
        if d.is_dir() and hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(str(d))
            except OSError:
                pass
    parts = [str(dll), str(root)]
    path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(parts + ([path] if path else []))
    tcl_lib = root / "tcl" / "$($tclLib.Name)"
    tk_lib = root / "tcl" / "$($tkLib.Name)"
    if tcl_lib.is_dir():
        os.environ.setdefault("TCL_LIBRARY", str(tcl_lib))
    if tk_lib.is_dir():
        os.environ.setdefault("TK_LIBRARY", str(tk_lib))

_anonymizer_tk_bootstrap()
"@
    $sitePath = Join-Path $dstSite "sitecustomize.py"
    [System.IO.File]::WriteAllText($sitePath, $siteCustom)
    Write-Ok "Wrote sitecustomize.py (DLL dirs + TCL_LIBRARY=$($tclLib.Name) TK_LIBRARY=$($tkLib.Name))"
}

Copy-TkinterIntoRuntime -HostPython $Py -RuntimeDir $Runtime

# import site runs sitecustomize (._pth has "import site")
$tkCheck = "import tkinter; r=tkinter.Tk(); r.withdraw(); r.destroy(); print('tkinter ok')"
& $PyEmbed -c $tkCheck
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Listing runtime DLLs for diagnosis..."
    Get-ChildItem -LiteralPath (Join-Path $Runtime "DLLs") -File -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Host "  runtime DLL: $($_.Name)" }
    Get-ChildItem -LiteralPath $Runtime -File -Filter "*.dll" -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Host "  runtime root: $($_.Name)" }
    Get-ChildItem -LiteralPath $Runtime -File -Filter "_tkinter*" -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Host "  runtime root: $($_.Name)" }
    Die "runtime tkinter check failed after copy - review-window would not work in Setup"
}
Write-Ok "Embeddable runtime has working tkinter"

Write-Info "Bootstrapping pip into embeddable runtime..."
& $PyEmbed $GetPip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { Die "get-pip.py failed" }

# Build the package wheel on the host (hatchling needs a full stdlib).
# Embeddable pip then installs the wheel + pure binary deps from PyPI.
$WheelDir = Join-Path $Cache "wheels"
if (Test-Path $WheelDir) { Remove-Item -Recurse -Force $WheelDir }
New-Item -ItemType Directory -Force -Path $WheelDir | Out-Null
Write-Info "Building anonymizer wheel on host..."
& $Py -m pip install -q "build>=1.0" "hatchling"
if ($LASTEXITCODE -ne 0) { Die "pip install build/hatchling failed" }
& $Py -m build --wheel --outdir $WheelDir "$Root"
if ($LASTEXITCODE -ne 0) { Die "python -m build failed" }
$wheel = Get-ChildItem -Path $WheelDir -Filter "anonymizer-*.whl" | Select-Object -First 1
if (-not $wheel) { Die "anonymizer wheel not produced in $WheelDir" }
Write-Ok "Wheel: $($wheel.Name)"

Write-Info "Installing anonymizer wheel into runtime..."
& $PyEmbed -m pip install --no-warn-script-location $wheel.FullName
if ($LASTEXITCODE -ne 0) { Die "pip install anonymizer wheel failed" }

$enCandidates = switch ($Models) {
    "lg" { @("en_core_web_lg", "en_core_web_md", "en_core_web_sm") }
    "md" { @("en_core_web_md", "en_core_web_sm") }
    default { @("en_core_web_sm") }
}
$fiCandidates = switch ($Models) {
    "lg" { @("fi_core_news_lg", "fi_core_news_md", "fi_core_news_sm") }
    "md" { @("fi_core_news_md", "fi_core_news_sm") }
    default { @("fi_core_news_sm") }
}
function Install-SpacyChain([string[]] $Candidates, [string] $Label) {
    foreach ($m in $Candidates) {
        Write-Info "Downloading spaCy model $m ($Label)..."
        & $PyEmbed -m spacy download $m
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Installed $m"
            return $true
        }
        Write-Warn "Failed $m - trying next fallback if any"
    }
    return $false
}
Write-Info ("Downloading spaCy models (size={0}; default lg for best NER quality)..." -f $Models)
if (-not (Install-SpacyChain $enCandidates "English")) { Die "Could not install English spaCy model" }
if (-not (Install-SpacyChain $fiCandidates "Finnish")) { Die "Could not install Finnish spaCy model" }

# Sanity: package imports without host Python.
# Use a variable + Python single-quoted strings: PowerShell re-quotes native
# args and strips "..." if they appear inside -c 'print("...")'.
$runtimeCheck = "import anonymizer, spacy; print('runtime ok', anonymizer.__version__)"
& $PyEmbed -c $runtimeCheck
if ($LASTEXITCODE -ne 0) { Die "runtime import check failed" }
Write-Ok "Embeddable runtime ready"

# CLI launcher - module form is relocatable (no hardcoded Scripts\*.exe paths)
$cmd = @"
@echo off
REM Anonymizer CLI - installed by Setup / build-release.ps1
"%~dp0..\runtime\python.exe" -m anonymizer.cli %*
exit /b %ERRORLEVEL%
"@
Set-Content -Path (Join-Path $Stage "bin\anonymize.cmd") -Value $cmd -Encoding ASCII
Write-Ok "bin\anonymize.cmd"

# --- freeze GUI ---
if (-not $SkipGuiFreeze) {
    # Host must have GUI imports (yaml etc.) so PyInstaller can collect them.
    # The freeze does NOT use the embeddable runtime - only the host env.
    Write-Info "Installing freeze deps into build host env (pyinstaller + pyyaml + package)..."
    & $Py -m pip install -q "pyinstaller>=6.0" "pyyaml>=6.0" $wheel.FullName
    if ($LASTEXITCODE -ne 0) { Die "pip install freeze deps failed" }
    $freezeCheck = "import yaml, anonymizer.gui, anonymizer.lists_io; print('freeze imports ok', yaml.__name__)"
    & $Py -c $freezeCheck
    if ($LASTEXITCODE -ne 0) { Die "host freeze import check failed (yaml/gui)" }
    Write-Info "Freezing Anonymizer.exe (GUI only)..."
    $spec = Join-Path $Root "packaging\windows\Anonymizer.spec"
    & $Py -m PyInstaller --noconfirm --clean --distpath (Join-Path $Stage "app") --workpath (Join-Path $Dist "pyi-work") $spec
    if ($LASTEXITCODE -ne 0) { Die "PyInstaller failed" }
    $guiExe = Join-Path $Stage "app\Anonymizer.exe"
    if (-not (Test-Path $guiExe)) {
        $alt = Get-ChildItem -Path (Join-Path $Stage "app") -Filter "Anonymizer.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($alt) { $guiExe = $alt.FullName }
    }
    if (-not (Test-Path $guiExe)) { Die "Anonymizer.exe not produced" }
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
REM Dev fallback - requires runtime python with tkinter (embeddable may lack it)
"%~dp0..\runtime\python.exe" -m anonymizer.gui %*
"@
    Set-Content -Path (Join-Path $Stage "bin\Anonymizer.cmd") -Value $guiCmd -Encoding ASCII
    Copy-Item (Join-Path $Stage "bin\Anonymizer.cmd") (Join-Path $Stage "Anonymizer.cmd")
}

# Version stamp
Set-Content -Path (Join-Path $Stage "VERSION") -Value $Version -Encoding ASCII -NoNewline

# Drop bytecode before packaging (smaller zip/Setup; avoids long-path ISCC aborts)
Write-Info "Cleaning __pycache__ / *.pyc from stage..."
Get-ChildItem -Path $Stage -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $Stage -Recurse -Include "*.pyc", "*.pyo" -File -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

# Zip portable stage
$zip = Join-Path $Dist "Anonymizer-$Version-windows.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Write-Info "Zipping $zip"
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $zip -Force
Write-Ok $zip

# --- Inno Setup ---
if ($SkipInstaller) {
    Write-Info "SkipInstaller set - stage + zip only"
    exit 0
}

$iscc = $null
foreach ($c in @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    (Get-Command iscc -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
)) {
    if ($c -and (Test-Path $c)) { $iscc = $c; break }
}
if (-not $iscc) {
    Write-Warn "Inno Setup (ISCC.exe) not found - install from https://jrsoftware.org/isinfo.php"
    Write-Warn ("Stage is ready at {0}; zip at {1}" -f $Stage, $zip)
    exit 0
}

# Deep repo paths can exceed MAX_PATH during ISCC compress; feed a short junction.
$StageForIscc = $Stage
$ShortJunction = "C:\anon-stage"
if ($Stage.Length -gt 80) {
    Write-Info "Creating short junction $ShortJunction -> stage (ISCC path length)"
    if (Test-Path $ShortJunction) {
        cmd /c "rmdir `"$ShortJunction`"" | Out-Null
    }
    cmd /c "mklink /J `"$ShortJunction`" `"$Stage`"" | Out-Null
    if (Test-Path $ShortJunction) {
        $StageForIscc = $ShortJunction
    } else {
        Write-Warn "Could not create junction; using full stage path"
    }
}

$iss = Join-Path $Root "packaging\windows\installer\anonymizer.iss"
Write-Info "Compiling installer with $iscc"
& $iscc "/DMyAppVersion=$Version" "/DMyStageDir=$StageForIscc" $iss
$isccCode = $LASTEXITCODE
if ($StageForIscc -eq $ShortJunction -and (Test-Path $ShortJunction)) {
    cmd /c "rmdir `"$ShortJunction`"" | Out-Null
}
if ($isccCode -ne 0) { Die "ISCC failed" }
$setup = Join-Path $Dist "Anonymizer-Setup-$Version.exe"
if (Test-Path $setup) {
    Write-Ok "Installer: $setup"
} else {
    $found = Get-ChildItem -Path $Dist -Filter "Anonymizer-Setup*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { Write-Ok "Installer: $($found.FullName)" }
    else { Write-Warn 'Setup exe not found in dist\ - check Inno OutputDir' }
}

Write-Ok "Windows release build finished"
