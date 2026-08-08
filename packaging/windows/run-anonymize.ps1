#Requires -Version 5.1
<#
.SYNOPSIS
  Resolve anonymize CLI and process one or more files (Windows helper for GUI).

.DESCRIPTION
  Parallel to packaging/macos/run-anonymize.sh.
  Prints OUTPUT:<path> lines for written files.

.EXAMPLE
  .\run-anonymize.ps1 -Format both strict C:\docs\a.pdf
  .\run-anonymize.ps1 -Review -RedactStyle placeholder standard .\memo.docx
#>
[CmdletBinding()]
param(
    [switch] $Review,
    [ValidateSet("placeholder", "remove")]
    [string] $RedactStyle = "",
    [ValidateSet("md", "source", "both", "native", "original", "dual")]
    [string] $Format = "",
    [string] $Config = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Rest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Find-Anonymize {
    if ($env:ANONYMIZER_BIN -and (Test-Path -LiteralPath $env:ANONYMIZER_BIN)) {
        return $env:ANONYMIZER_BIN
    }
    $cmd = Get-Command anonymize -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($name in @("Anonymizer", "anonymizer")) {
        $local = Join-Path $env:LOCALAPPDATA "$name\bin\anonymize.cmd"
        if (Test-Path -LiteralPath $local) { return $local }
        $rt = Join-Path $env:LOCALAPPDATA "$name\runtime\Scripts\anonymize.exe"
        if (Test-Path -LiteralPath $rt) { return $rt }
    }
    $venv = Join-Path $PSScriptRoot "..\..\.venv\Scripts\anonymize.exe"
    if (Test-Path -LiteralPath $venv) { return (Resolve-Path $venv).Path }
    throw "could not find anonymize CLI. Install with scripts\install.ps1 first."
}

function Normalize-Mode([string] $Raw) {
    switch -Regex ($Raw.ToLowerInvariant()) {
        '^(strict|scrub|full)$' { return "strict" }
        '^(standard|normal|pii)$' { return "standard" }
        '^(extract|text|plain)$' { return "extract" }
        default { return $null }
    }
}

function Expected-MdPath([string] $InputPath, [string] $Mode) {
    $dir = Split-Path -Parent $InputPath
    $base = [IO.Path]::GetFileNameWithoutExtension($InputPath)
    $ext = [IO.Path]::GetExtension($InputPath)
    if ($Mode -eq "extract") {
        $name = "$base.md"
        if ((Join-Path $dir $name) -eq $InputPath) { $name = "$base.extracted.md" }
    } else {
        $name = "$base.anonymized.md"
    }
    return (Join-Path $dir $name)
}

function Expected-NativePath([string] $InputPath) {
    $ext = [IO.Path]::GetExtension($InputPath).ToLowerInvariant()
    if ($ext -notin @(".pdf", ".docx")) { return $null }
    $dir = Split-Path -Parent $InputPath
    $base = [IO.Path]::GetFileNameWithoutExtension($InputPath)
    return (Join-Path $dir "$base.anonymized$ext")
}

# Parse remaining: [mode] file [file...]
$mode = "strict"
$files = @()
if ($Rest -and $Rest.Count -ge 1) {
    $maybe = Normalize-Mode $Rest[0]
    if ($maybe) {
        $mode = $maybe
        $files = @($Rest | Select-Object -Skip 1)
    } else {
        $files = @($Rest)
    }
}
if (-not $files -or $files.Count -eq 0) {
    Write-Error "Usage: run-anonymize.ps1 [options] [mode] file [file ...]"
    exit 2
}

$bin = Find-Anonymize
$extra = @()
if ($Config) { $extra += @("--config", $Config) }
if ($RedactStyle) { $extra += @("--redact-style", $RedactStyle) }
if ($Format) {
    $fmt = $Format
    if ($fmt -in @("native", "original")) { $fmt = "source" }
    if ($fmt -eq "dual") { $fmt = "both" }
    $extra += @("--format", $fmt)
}

$ok = 0
$fail = 0
$outputs = New-Object System.Collections.Generic.List[string]

foreach ($f in $files) {
    if (-not (Test-Path -LiteralPath $f)) {
        Write-Host "error: path not found: $f" -ForegroundColor Red
        $fail++
        continue
    }
    $abs = (Resolve-Path -LiteralPath $f).Path
    $args = @($mode, $abs) + $extra
    if ($Review) { $args += "--review" }
    else { $args += "--quiet" }

    try {
        & $bin @args
        if ($LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }
        $fmtUse = if ($Format) { $Format } else { "md" }
        if ($fmtUse -notin @("source", "native", "original")) {
            $md = Expected-MdPath $abs $mode
            if (Test-Path -LiteralPath $md) {
                Write-Output "OUTPUT:$md"
                $outputs.Add($md)
            }
        }
        if ($fmtUse -in @("source", "native", "original", "both", "dual")) {
            $nat = Expected-NativePath $abs
            if ($nat -and (Test-Path -LiteralPath $nat)) {
                Write-Output "OUTPUT:$nat"
                $outputs.Add($nat)
            }
        }
        $ok++
    } catch {
        Write-Host "error: anonymize failed for: $abs — $_" -ForegroundColor Red
        $fail++
    }
}

if ($fail -gt 0) {
    Write-Host "done: $ok ok, $fail failed (mode=$mode)" -ForegroundColor Yellow
    exit 1
}
Write-Host "done: $ok file(s) ok (mode=$mode)" -ForegroundColor Green

if ($env:ANONYMIZER_OPEN -match '^(1|y|yes)$' -and $outputs.Count -gt 0) {
    foreach ($o in $outputs) {
        Invoke-Item -LiteralPath $o
    }
}
